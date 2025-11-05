# orchestration/router.py
# Intent/slot 분석을 바탕으로 Retrieval/Compute를 호출하는 LangGraph 라우터

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal, Optional, Protocol

from src.core.exceptions import InvalidValueError
from src.core.metrics import track_latency, track_tokens
from src.nlp.slot_intent import extract_intent_and_slots

from .state import OrchestrationState

logger = logging.getLogger(__name__)


class RetrievalRunner(Protocol):
    """검색 노드에서 사용되는 인터페이스."""

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class ComputeRunner(Protocol):
    """계산 노드에서 사용되는 인터페이스."""

    def run(
        self,
        *,
        category: str | None,
        params: dict[str, Any] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class RouterConfig:
    info_score_threshold: float = 0.55
    fallback_message: str = "현재는 답변을 생성하지 못했습니다. 내용을 조금 더 구체적으로 알려주시면 다시 시도할게요."
    require_params_for_calc: bool = True
    require_fields_for_calc: tuple[str, ...] = (
        "property_value",
        "annual_income",
        "existing_debt_payment",
        "interest_rate",
        "term_months",
        "repayment_type",
        "region",
        "occupancy",
        "house_count",
    )


DEFAULT_CONFIG = RouterConfig()

LOW_CONFIDENCE_CODE = "retrieval_low_confidence"
MISSING_PARAMS_CODE = "missing_params"
RETRIEVAL_ERROR_CODE = "retrieval_error"
COMPUTE_ERROR_CODE = "compute_error"
INTENT_ERROR_CODE = "intent_resolution_failed"


def route(
    state: OrchestrationState,
    *,
    retriever: Optional[RetrievalRunner],
    compute: Optional[ComputeRunner],
    config: RouterConfig | None = None,
    intent_hint: Optional[Literal["calc", "info"]] = None,
) -> OrchestrationState:
    config = config or DEFAULT_CONFIG

    if not state.user_query:
        return _fallback(state, config, code=INTENT_ERROR_CODE, reason="empty_query")

    state.inputs = dict(state.inputs or {})
    if state.inputs:
        for key, value in state.inputs.items():
            state.slots.setdefault(key, value)

    analysis: dict[str, Any] | None = None

    # 1) Intent/slot 분석
    if intent_hint:
        state.intent = intent_hint
        state.mode = intent_hint
    else:
        intent_started = perf_counter()
        raw = extract_intent_and_slots(state.user_query)
        intent_elapsed = (perf_counter() - intent_started) * 1000.0
        track_latency("intent_analysis", value=intent_elapsed)
        _record_latency(state, "intent_analysis_ms", intent_elapsed)
        analysis = raw if isinstance(raw, dict) else None

    if isinstance(analysis, dict):
        candidate_intent = analysis.get("intent")
        if isinstance(candidate_intent, str):
            state.intent = candidate_intent
        if state.intent not in {"info", "calc"}:
            state.intent = "info"
        state.mode = state.intent
        slots = analysis.get("slots")
        if isinstance(slots, dict):
            state.slots.update(slots)
            state.inputs = {**state.inputs, **slots}
        confidence = analysis.get("confidence")
        if isinstance(confidence, dict):
            state.metrics["intent_confidence"] = confidence
            state.metrics.setdefault("intent_signals", {})["confidence_score"] = confidence.get("score")
            state.reason = confidence.get("reason")
    else:
        state.intent = state.intent or "info"
        state.mode = state.intent

    if not _is_housing_related(state.user_query, state.slots):
        state = _fallback(
            state,
            config,
            code=INTENT_ERROR_CODE,
            reason="out_of_domain",
            details={"query": state.user_query},
        )
        state.response_message = (
            "이 챗봇은 주택담보대출 한도와 정책 안내 전용입니다. "
            "관련 대출 질문으로 다시 요청해 주세요."
        )
        return state

    _maybe_force_calc(state, analysis)
    state.metrics.setdefault("intent_signals", {})["forced_calc"] = state.mode == "calc"

    # 2) Intent에 따라 분기
    if state.mode == "info":
        return _handle_information(state, retriever, compute, config)
    if state.mode == "calc":
        return _handle_calculation(state, compute, config)

    return _fallback(state, config, code=INTENT_ERROR_CODE, reason="unsupported_mode", details={"mode": state.mode})


def _handle_information(
    state: OrchestrationState,
    retriever: Optional[RetrievalRunner],
    compute: Optional[ComputeRunner],
    config: RouterConfig,
) -> OrchestrationState:
    if retriever is None:
        return _fallback(state, config, code=RETRIEVAL_ERROR_CODE, reason="retriever_missing")

    try:
        started = perf_counter()
        result = retriever.run(category=state.category, query=state.user_query)
        elapsed = (perf_counter() - started) * 1000.0
        track_latency("retrieval", value=elapsed)
        _record_latency(state, "retrieval_ms", elapsed)
    except InvalidValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Retriever 실행 중 오류: query=%s category=%s", state.user_query, state.category)
        return _fallback(state, config, code=RETRIEVAL_ERROR_CODE, reason="exception", error=str(exc))

    state.response_data = result or {}
    state.answer = result.get("answer")
    state.documents = list(result.get("documents") or [])
    state.web_results = list(result.get("web_results") or [])
    state.sources = list(result.get("sources") or [])
    state.confidence = result.get("confidence")
    if isinstance(state.confidence, dict):
        state.reason = state.confidence.get("reason")

    _record_token_usage(state, "retrieval", result)

    score = _extract_confidence_score(state.confidence)
    passed = bool(state.confidence.get("passed")) if isinstance(state.confidence, dict) else False

    if passed or (score is not None and score >= config.info_score_threshold):
        state.response_message = state.answer or "관련 정보를 찾았습니다."
        return state

    if state.web_results:
        state.response_message = "내부 문서 신뢰도가 낮아 웹 검색 결과를 우선으로 안내드릴게요."
        state.documents = []
        state.sources = _collect_web_sources(state.web_results)
        state.reason = LOW_CONFIDENCE_CODE
        return state

    if compute and _should_retry_as_calc(state):
        state.metrics.setdefault("intent_signals", {})["info_to_calc_retry"] = True
        state.mode = "calc"
        state.intent = "calc"
        return _handle_calculation(state, compute, config)

    return _fallback(
        state,
        config,
        code=LOW_CONFIDENCE_CODE,
        reason="score_below_threshold",
        details={"score": score, "threshold": config.info_score_threshold},
    )


def _handle_calculation(
    state: OrchestrationState,
    compute: Optional[ComputeRunner],
    config: RouterConfig,
) -> OrchestrationState:
    if compute is None:
        return _fallback(state, config, code=COMPUTE_ERROR_CODE, reason="compute_missing")

    params = state.inputs or {}
    if config.require_params_for_calc and not params:
        state = _fallback(state, config, code=MISSING_PARAMS_CODE, reason="params_required")
        state.response_message = _build_missing_params_message(list(config.require_fields_for_calc))
        state.response_data = {
            "status": "need_inputs",
            "code": MISSING_PARAMS_CODE,
            "reason": "params_required",
            "missing": list(config.require_fields_for_calc),
        }
        state.metrics["missing_fields"] = list(config.require_fields_for_calc)
        return state

    missing = _missing_calc_fields(params, config.require_fields_for_calc)
    if missing:
        state = _fallback(
            state,
            config,
            code=MISSING_PARAMS_CODE,
            reason="missing_required_inputs",
            details={"missing": missing},
        )
        state.response_message = _build_missing_params_message(missing)
        state.response_data = {
            "status": "need_inputs",
            "code": MISSING_PARAMS_CODE,
            "reason": "missing_required_inputs",
            "missing": missing,
        }
        state.metrics["missing_fields"] = missing
        return state

    try:
        started = perf_counter()
        result = compute.run(category=state.category, params=params)
        elapsed = (perf_counter() - started) * 1000.0
        track_latency("compute", value=elapsed)
        _record_latency(state, "compute_ms", elapsed)
    except InvalidValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Compute 실행 중 오류: category=%s params=%s", state.category, params)
        return _fallback(state, config, code=COMPUTE_ERROR_CODE, reason="exception", error=str(exc))

    state.calc = result or {}
    state.sources = list(result.get("sources") or [])
    state.confidence = result.get("confidence")
    if isinstance(state.confidence, dict):
        state.reason = state.confidence.get("reason")
    state.response_data = result
    state.response_message = result.get("summary") or "계산 결과를 정리했습니다."
    _record_token_usage(state, "compute", result)
    return state


def _fallback(
    state: OrchestrationState,
    config: RouterConfig,
    *,
    code: str,
    reason: str,
    error: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> OrchestrationState:
    state.response_message = config.fallback_message
    state.response_text = ""
    entry: dict[str, Any] = {"code": code, "reason": reason}
    if error:
        entry["error"] = error
    if details:
        entry["details"] = details
    state.errors.append(entry)
    state.response_data = {
        "status": "fallback",
        "code": code,
        "reason": reason,
        "details": details or {},
    }
    state.metrics.setdefault("errors", []).append(entry)
    return state


def _extract_confidence_score(confidence: Any) -> Optional[float]:
    if not isinstance(confidence, dict):
        return None
    score = confidence.get("score") or confidence.get("top_score_normalized") or confidence.get("top_score")
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


def _collect_web_sources(web_results: list[dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    for item in web_results:
        url = item.get("url")
        title = item.get("title")
        if url and title:
            sources.append(f"{title} ({url})")
        elif url:
            sources.append(url)
    return sources


def _record_latency(state: OrchestrationState, key: str, value_ms: float) -> None:
    latencies = state.metrics.setdefault("latency_ms", {})
    latencies[key] = round(float(value_ms), 3)


def _record_token_usage(state: OrchestrationState, prefix: str, payload: dict[str, Any] | None) -> None:
    if not payload or not isinstance(payload, dict):
        return
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    try:
        prompt_tokens = int(prompt) if prompt is not None else 0
        completion_tokens = int(completion) if completion is not None else 0
    except (TypeError, ValueError):
        return
    if prompt_tokens == 0 and completion_tokens == 0:
        return
    track_tokens(prefix, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    token_usage = state.metrics.setdefault("token_usage", {})
    token_usage[prefix] = {
        "prompt": prompt_tokens,
        "completion": completion_tokens,
    }


def _is_housing_related(query: str, slots: dict[str, Any]) -> bool:
    """주택담보대출 도메인과 무관한 질문을 빠르게 걸러낸다."""

    normalized = (query or "").lower()
    housing_keywords = {
        "주택",
        "집",
        "아파트",
        "전세",
        "담보",
        "대출",
        "한도",
        "ltv",
        "dti",
        "dsr",
        "모기지",
        "지분적립형",
        "디딤돌",
        "보금자리",
        "금리",
        "대환",
    }
    if any(keyword in normalized for keyword in housing_keywords):
        return True

    slot_keys = set((slots or {}).keys())
    relevant_slots = {
        "loan_amount",
        "collateral_value",
        "annual_income",
        "interest_rate",
        "house_price",
        "mortgage_type",
        "region",
        "ltv",
        "dti",
        "dsr",
    }
    return bool(slot_keys & relevant_slots)


def _maybe_force_calc(state: OrchestrationState, analysis: dict[str, Any] | None) -> None:
    """정보형으로 분류됐더라도 수치 신호가 강하면 계산형으로 전환한다."""

    if state.mode == "calc":
        return

    slots = state.slots or {}
    has_amount = isinstance(slots.get("loan_amount"), (int, float))
    has_interest = isinstance(slots.get("interest_rate"), (int, float))
    has_term = isinstance(slots.get("term_months"), int) and slots.get("term_months") > 0

    calc_bias = sum(
        1 for flag in (has_amount, has_interest, has_term) if flag
    )

    confidence_score = None
    if isinstance(analysis, dict):
        confidence = analysis.get("confidence")
        if isinstance(confidence, dict):
            try:
                confidence_score = float(confidence.get("score")) if confidence.get("score") is not None else None
            except (TypeError, ValueError):
                confidence_score = None

    if confidence_score is not None and confidence_score >= 0.7 and analysis and analysis.get("intent") == "calc":
        state.intent = "calc"
        state.mode = "calc"
        state.metrics.setdefault("intent_signals", {})["forced_calc_reason"] = "llm_high_confidence"
        return

    if calc_bias >= 1:
        state.intent = "calc"
        state.mode = "calc"
        state.metrics.setdefault("intent_signals", {})["forced_calc_reason"] = {
            "calc_bias": calc_bias,
            "confidence_score": confidence_score,
        }


def _missing_calc_fields(params: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for key in required:
        value = params.get(key)
        if value in (None, "", []):
            missing.append(key)
    return missing


def _build_missing_params_message(missing: list[str]) -> str:
    labels = {
        "property_value": "주택가격(또는 담보평가액)",
        "annual_income": "연소득",
        "existing_debt_payment": "기존 부채 월상환액",
        "interest_rate": "희망 금리(연)",
        "term_months": "상환 기간(개월)",
        "repayment_type": "상환 방식",
        "region": "지역/규제구역",
        "occupancy": "실거주 여부",
        "house_count": "보유 주택 수",
    }

    if not missing:
        return "계산을 진행할 수 있도록 필요한 정보를 조금 더 알려주세요."

    readable = [labels.get(item, item) for item in missing]
    joined = ", ".join(readable)
    return f"계산 결과를 위해 다음 정보를 알려주시면 한도를 산출할 수 있어요: {joined}."


def _should_retry_as_calc(state: OrchestrationState) -> bool:
    """정보형 검색 신뢰도가 낮을 때 계산형으로 재시도할지 판단."""

    slots = state.slots or {}
    if not slots:
        return False
    has_amount = isinstance(slots.get("loan_amount"), (int, float))
    has_interest = isinstance(slots.get("interest_rate"), (int, float))
    has_term = isinstance(slots.get("term_months"), int) and slots.get("term_months") > 0
    calc_signals = sum(1 for flag in (has_amount, has_interest, has_term) if flag)
    if calc_signals < 2:
        return False
    if state.metrics.get("intent_signals", {}).get("info_to_calc_retry"):
        return False
    return True


__all__ = ["route", "RouterConfig", "DEFAULT_CONFIG"]
