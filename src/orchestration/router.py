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

    # 1) Intent/slot 분석
    if intent_hint:
        state.intent = intent_hint
        state.mode = intent_hint
    else:
        intent_started = perf_counter()
        analysis = extract_intent_and_slots(state.user_query)
        intent_elapsed = (perf_counter() - intent_started) * 1000.0
        track_latency("intent_analysis", value=intent_elapsed)
        _record_latency(state, "intent_analysis_ms", intent_elapsed)
        state.intent = (analysis.get("intent") or "info") if isinstance(analysis, dict) else "info"
        if state.intent not in {"info", "calc"}:
            state.intent = "info"
        state.mode = state.intent
        slots = analysis.get("slots") if isinstance(analysis, dict) else None
        if isinstance(slots, dict):
            state.slots.update(slots)
            state.inputs = {**state.inputs, **slots}
        confidence = analysis.get("confidence") if isinstance(analysis, dict) else None
        if confidence:
            state.metrics["intent_confidence"] = confidence
            state.reason = confidence.get("reason")

    # 2) Intent에 따라 분기
    if state.mode == "info":
        return _handle_information(state, retriever, config)
    if state.mode == "calc":
        return _handle_calculation(state, compute, config)

    return _fallback(state, config, code=INTENT_ERROR_CODE, reason="unsupported_mode", details={"mode": state.mode})


def _handle_information(
    state: OrchestrationState,
    retriever: Optional[RetrievalRunner],
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
        return _fallback(state, config, code=MISSING_PARAMS_CODE, reason="params_required")

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


__all__ = ["route", "RouterConfig", "DEFAULT_CONFIG"]
