"""Chat 서비스 계층."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from time import perf_counter
from typing import Any, Protocol

from src.api.schemas import (
    ChatIntent,
    ChatRequest,
    ChatResponse,
    build_chat_response,
    CalcType,
)
from src.core.exceptions import InvalidValueError
from src.nlp.slot_intent import extract_intent_and_slots
from src.retrieval.pipeline import RetrievalPipeline
from src.services.compute_service import ComputeService, get_compute_service
from src.services.retriever_service import PipelineRetriever
from src.websearch.config import WebSearchConfig, load_websearch_config
from src.websearch.provider import create_requests_provider
from src.websearch.search import SearchProvider


INFORMATIONAL_CATEGORIES = {"loan_limit", "interest_rate"}

CALC_CATEGORY_MAP: dict[str, CalcType] = {
    "monthly_payment": CalcType.AMORTIZATION,
    "ltv": CalcType.LTV,
    "dti": CalcType.DTI,
    "dsr": CalcType.DSR,
    "amortization": CalcType.AMORTIZATION,
    "payment_sensitivity": CalcType.PAYMENT_SENSITIVITY,
}

CALCULATIONAL_CATEGORIES = set(CALC_CATEGORY_MAP.keys())

CALC_REQUIRED_PARAMS: dict[CalcType, list[str]] = {
    CalcType.LTV: ["collateral_value", "loan_amount"],
    CalcType.DTI: ["annual_income", "total_debt_payment"],
    CalcType.DSR: ["annual_income", "annual_debt_service"],
    CalcType.AMORTIZATION: ["principal", "interest_rate", "months"],
    CalcType.PAYMENT_SENSITIVITY: ["principal", "interest_rates", "months"],
}

CALC_PARAM_LABELS: dict[str, str] = {
    "category": "계산 유형",
    "collateral_value": "담보 가치",
    "loan_amount": "대출 금액",
    "annual_income": "연소득",
    "total_debt_payment": "총 부채 상환액",
    "annual_debt_service": "연간 부채 상환액",
    "principal": "대출 원금",
    "interest_rate": "연 이자율(%)",
    "interest_rates": "이자율 목록",
    "months": "상환 개월 수",
}


logger = logging.getLogger(__name__)
ENV_TOKEN_PATTERN = re.compile(r"\$\{([^}]+)\}")
_ENV_LOADED = False


class RetrievalRunner(Protocol):
    """정보형 intent에 사용되는 검색 모듈 인터페이스."""

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class ComputeRunner(Protocol):
    """계산형 intent에 사용되는 연산 모듈 인터페이스."""

    def run(
        self,
        *,
        category: str | None,
        params: dict[str, Any] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class MockRetriever:
    """Iteration 2에서 사용되는 기본 Mock Retrieval."""

    is_mock = True

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
            "sources": [
                "https://example.com/loan-guidelines",
                "https://example.com/credit-score",
            ],
            "query": query,
        }


class ChatService:
    """챗봇 intent에 따라 적절한 모듈을 호출한다."""

    def __init__(
        self,
        *,
        retriever: RetrievalRunner,
        compute: ComputeRunner,
    ) -> None:
        self._retriever = retriever
        self._compute = compute

    def handle(self, request: ChatRequest) -> ChatResponse:
        """요청 intent에 맞춰 응답을 생성한다."""

        generated_at = datetime.now(timezone.utc)
        if not _is_housing_related(request.message, request.category):
            payload = {
                "answer": (
                    "이 챗봇은 주택담보대출 한도와 정책 안내 전용입니다. "
                    "관련 대출 질문으로 다시 요청해 주세요."
                ),
                "sources": [],
            }
            return build_chat_response(
                intent=ChatIntent.INFORMATIONAL,
                category=request.category,
                data=payload,
                message="도메인 외 질문을 안내 문구로 처리했습니다.",
                generated_at=generated_at,
                mock=True,
            )

        resolution = _resolve_intent(request)
        intent = resolution.intent

        if intent == ChatIntent.INFORMATIONAL:
            if request.category and request.category not in INFORMATIONAL_CATEGORIES:
                raise InvalidValueError(
                    "지원하지 않는 category 입니다.",
                    field="category",
                    details={"category": request.category},
                )

            started = perf_counter()
            retrieval_payload = self._retriever.run(
                category=request.category,
                query=request.message,
            )
            elapsed_ms = round((perf_counter() - started) * 1000.0, 3)
            retrieval_payload = _attach_latency(retrieval_payload, elapsed_ms)
            retrieval_payload = _attach_intent_metadata(retrieval_payload, resolution)
            return build_chat_response(
                intent=intent,
                category=request.category,
                data=retrieval_payload,
                message="정보형 답변을 생성했습니다.",
                generated_at=generated_at,
                mock=getattr(self._retriever, "is_mock", False),
            )

        if intent == ChatIntent.CALCULATIONAL:
            params = _prepare_calc_params(request, resolution)
            inferred_category = _infer_calc_category(request, resolution, params)
            request_category = _normalize_calc_category_token(request.category)
            normalized_category = inferred_category or request_category
            calc_type: CalcType | None = None
            if normalized_category:
                calc_type = CALC_CATEGORY_MAP.get(normalized_category)
            response_category = normalized_category or request.category

            missing: list[str] = []
            if calc_type is None:
                missing.append("category")
            else:
                required = CALC_REQUIRED_PARAMS.get(calc_type, [])
                for key in required:
                    if _is_missing_param(params, key):
                        if key not in missing:
                            missing.append(key)

            if not params:
                for key in (CALC_REQUIRED_PARAMS.get(calc_type, []) if calc_type else []):
                    if key not in missing:
                        missing.append(key)

            if missing:
                compute_payload = {
                    "needs_input": True,
                    "missing_params": missing,
                    "calc_type": calc_type.value if calc_type else None,
                    "params": params,
                }
            else:
                started = perf_counter()
                compute_payload = self._compute.run(
                    category=normalized_category,
                    params=params,
                )
                elapsed_ms = round((perf_counter() - started) * 1000.0, 3)
                compute_payload = _attach_latency(compute_payload, elapsed_ms)
                if not compute_payload.get("needs_input") and calc_type is not None:
                    summary_payload = _summarize_compute_result(calc_type, compute_payload)
                    if summary_payload:
                        summary_text = summary_payload.get("text")
                        if summary_text:
                            compute_payload["summary"] = summary_text
                        primary_value = summary_payload.get("value")
                        if primary_value is not None:
                            compute_payload["primary_value"] = primary_value
                        unit = summary_payload.get("unit")
                        if unit:
                            compute_payload["primary_value_unit"] = unit
                        highlights = summary_payload.get("highlights")
                        if highlights:
                            compute_payload["highlights"] = highlights
            compute_payload = _attach_intent_metadata(compute_payload, resolution)
            message = "계산형 답변을 생성했습니다."
            if compute_payload.get("needs_input"):
                missing = compute_payload.get("missing_params") or []
                message = _build_missing_param_message(missing, resolution)
            return build_chat_response(
                intent=intent,
                category=response_category,
                data=compute_payload,
                message=message,
                generated_at=generated_at,
                mock=getattr(self._compute, "is_mock", False),
            )

        raise InvalidValueError("의도를 판별하지 못했습니다.", field="intent")


@lru_cache(maxsize=1)
def _get_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline()


@lru_cache(maxsize=1)
def _get_retriever() -> RetrievalRunner:
    pipeline = _get_retrieval_pipeline()
    web_config: WebSearchConfig | None = None
    web_provider: SearchProvider | None = None
    try:
        _ensure_env_loaded()
        raw_config = load_websearch_config()
        resolved_config = _resolve_websearch_config(raw_config)
        if resolved_config is not None:
            web_config = resolved_config
            web_provider = create_requests_provider(web_config.provider)
    except Exception as exc:  # noqa: BLE001
        logger.warning("웹 검색 초기화 실패, 로컬 문서만 사용합니다: %s", exc)
    return PipelineRetriever(
        pipeline=pipeline,
        web_provider=web_provider,
        web_config=web_config,
    )


@lru_cache(maxsize=1)
def _get_compute() -> ComputeRunner:
    compute_service = get_compute_service()

    class _ComputeAdapter(ComputeRunner):
        is_mock = False

        def run(
            self,
            *,
            category: str | None,
            params: dict[str, Any] | None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            params = _normalize_calc_params(dict(params or {}))
            calc_type = _resolve_calc_type(category)
            required = CALC_REQUIRED_PARAMS.get(calc_type, [])
            missing = [key for key in required if _is_missing_param(params, key)]
            if missing:
                return {
                    "needs_input": True,
                    "missing_params": missing,
                    "calc_type": calc_type.value,
                    "params": params,
                }
            result = compute_service.calculate(calc_type=calc_type, params=params)
            return {
                "needs_input": False,
                "result": result,
                "calc_type": calc_type.value,
                "params": params,
            }

    return _ComputeAdapter()


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    """FastAPI DI에 사용할 기본 ChatService 제공자."""

    return ChatService(retriever=_get_retriever(), compute=_get_compute())


def _attach_latency(payload: dict[str, Any] | None, elapsed_ms: float) -> dict[str, Any]:
    """응답 페이로드에 latency 정보를 주입한다."""

    payload = dict(payload or {})
    payload["elapsed_ms"] = elapsed_ms
    metrics = dict(payload.get("metrics") or {})
    metrics.setdefault("latency_ms", {})
    if isinstance(metrics["latency_ms"], dict):
        metrics["latency_ms"]["total_ms"] = elapsed_ms
    payload["metrics"] = metrics
    return payload


@dataclass(frozen=True)
class IntentResolution:
    intent: ChatIntent
    source: str
    slots: dict[str, Any]
    confidence: dict[str, Any]


def _resolve_intent(request: ChatRequest) -> IntentResolution:
    if request.intent is not None:
        return IntentResolution(
            intent=request.intent,
            source="client",
            slots={},
            confidence={},
        )

    if request.category in INFORMATIONAL_CATEGORIES:
        return IntentResolution(
            intent=ChatIntent.INFORMATIONAL,
            source="category_hint",
            slots={},
            confidence={},
        )

    if request.category in CALCULATIONAL_CATEGORIES:
        return IntentResolution(
            intent=ChatIntent.CALCULATIONAL,
            source="category_hint",
            slots={},
            confidence={},
        )

    try:
        analysis = extract_intent_and_slots(request.message)
    except Exception:  # noqa: BLE001
        analysis = {}

    slots = analysis.get("slots") if isinstance(analysis, dict) else {}
    confidence = analysis.get("confidence") if isinstance(analysis, dict) else {}
    intent_token = ""
    if isinstance(analysis, dict):
        intent_token = str(analysis.get("intent") or "").lower()

    calc_tokens = {"calc", "calculational", "calculate", "calculation"}
    info_tokens = {"info", "informational", "information"}

    if intent_token in calc_tokens:
        resolved_intent = ChatIntent.CALCULATIONAL
    elif intent_token in info_tokens:
        resolved_intent = ChatIntent.INFORMATIONAL
    else:
        resolved_intent = ChatIntent.INFORMATIONAL

    return IntentResolution(
        intent=resolved_intent,
        source="classifier",
        slots=_ensure_mapping(slots),
        confidence=_ensure_mapping(confidence),
    )


def _prepare_calc_params(request: ChatRequest, resolution: IntentResolution) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if request.params:
        params.update(request.params)
    # calc_type/category hints should not be treated as numeric params
    params.pop("calc_type", None)
    params.pop("category", None)
    if resolution.slots:
        for key, value in resolution.slots.items():
            params.setdefault(key, value)
    return _normalize_calc_params(params)


def _attach_intent_metadata(
    payload: dict[str, Any] | None,
    resolution: IntentResolution,
) -> dict[str, Any]:
    payload = dict(payload or {})

    intent_meta: dict[str, Any] = {"source": resolution.source}
    if resolution.slots:
        intent_meta["slots"] = dict(resolution.slots)
    if resolution.confidence:
        intent_meta["confidence"] = dict(resolution.confidence)
    payload["intent_resolution"] = intent_meta

    metrics = dict(payload.get("metrics") or {})
    raw_intent_metrics = metrics.get("intent")
    intent_metrics = dict(raw_intent_metrics) if isinstance(raw_intent_metrics, dict) else {}
    intent_metrics["source"] = resolution.source
    if resolution.confidence:
        intent_metrics["confidence"] = dict(resolution.confidence)
    metrics["intent"] = intent_metrics
    payload["metrics"] = metrics
    return payload


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _resolve_calc_type(category: str | None) -> CalcType:
    if category:
        normalized = category.strip().lower()
        if normalized in CALC_CATEGORY_MAP:
            return CALC_CATEGORY_MAP[normalized]
        try:
            return CalcType(normalized)
        except ValueError:
            raise InvalidValueError(
                "지원하지 않는 계산 카테고리 입니다.",
                field="category",
                details={"category": category},
            )
    raise InvalidValueError("계산형 intent에는 category가 필요합니다.", field="category")


def _build_missing_param_message(missing: list[str], resolution: IntentResolution) -> str:
    if not missing:
        return "계산 결과를 생성했습니다."
    labels = [_humanize_param_name(name) for name in missing]
    joined = ", ".join(labels)
    return f"계산을 완료하려면 다음 정보를 알려 주세요: {joined}"


def _humanize_param_name(name: str) -> str:
    return CALC_PARAM_LABELS.get(name, name)


def _normalize_calc_params(params: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str):
            normalized[key] = value.strip()
        else:
            normalized[key] = value

    def _apply_aliases() -> None:
        def _copy_if_missing(source: str, target: str) -> None:
            if source not in normalized:
                return
            if _is_empty_value(normalized[source]):
                return
            if target not in normalized or _is_empty_value(normalized[target]):
                normalized[target] = normalized[source]

        _copy_if_missing("loan_amount", "principal")
        _copy_if_missing("principal", "loan_amount")
        _copy_if_missing("term_months", "months")
        _copy_if_missing("months", "term_months")
        _copy_if_missing("rate", "interest_rate")
        _copy_if_missing("interest_rate", "rate")
        _copy_if_missing("property_value", "collateral_value")
        _copy_if_missing("collateral_value", "property_value")
        _copy_if_missing("existing_debt_payment", "total_debt_payment")
        _copy_if_missing("total_debt_payment", "existing_debt_payment")

    _apply_aliases()

    for key in ("months", "term_months"):
        if key in normalized:
            normalized[key] = _coerce_int(normalized[key])
    for key in ("interest_rate", "rate"):
        if key in normalized:
            normalized[key] = _coerce_float(normalized[key])

    _apply_aliases()

    _fill_collateral_and_loan_amounts(normalized)

    _apply_aliases()

    return normalized


def _fill_collateral_and_loan_amounts(params: dict[str, Any]) -> None:
    """추출된 수치 정보를 활용해 담보 가치/대출 금액을 보완한다."""

    additional = params.get("additional_amounts")
    if not isinstance(additional, (list, tuple)) or not additional:
        return

    candidates: list[tuple[str, float, Any]] = []

    def _add_candidate(key: str, raw: Any) -> None:
        if _is_empty_value(raw):
            return
        numeric = _to_numeric(raw)
        if numeric is None:
            return
        candidates.append((key, numeric, raw))

    if not _is_empty_value(params.get("loan_amount")):
        _add_candidate("loan_amount", params["loan_amount"])
    elif not _is_empty_value(params.get("principal")):
        _add_candidate("principal", params["principal"])

    for item in additional:
        _add_candidate("additional", item)

    # 이미 담보 가치가 명시된 경우에는 보정할 필요가 없다.
    if not _is_empty_value(params.get("collateral_value")):
        return

    if len(candidates) < 2:
        return

    candidates.sort(key=lambda item: item[1], reverse=True)
    collateral_candidate = candidates[0]
    loan_candidate = candidates[1]

    collateral_value = collateral_candidate[2]
    collateral_numeric = _to_numeric(collateral_value)
    if collateral_numeric is not None:
        params["collateral_value"] = int(round(collateral_numeric))
    else:
        params["collateral_value"] = collateral_value

    current_loan_numeric = _to_numeric(params.get("loan_amount"))
    loan_value = loan_candidate[2]
    loan_numeric = _to_numeric(loan_value)
    if (
        _is_empty_value(params.get("loan_amount"))
        or current_loan_numeric is None
        or (
            collateral_numeric is not None
            and current_loan_numeric == collateral_numeric
            and loan_numeric is not None
        )
    ):
        if loan_numeric is not None:
            params["loan_amount"] = int(round(loan_numeric))
        else:
            params["loan_amount"] = loan_value


def _summarize_compute_result(
    calc_type: CalcType,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """계산 결과를 사용자 친화적인 요약 형태로 변환한다."""

    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    def _highlight(label: str, value: str | None) -> dict[str, str] | None:
        if not value:
            return None
        return {"label": label, "value": value}

    highlights: list[dict[str, str]] = []

    if calc_type is CalcType.LTV:
        ratio = _to_numeric(result.get("ltv")) or _to_numeric(result.get("ratio"))
        if ratio is None:
            return None
        percent_value = ratio * 100.0
        collateral = (
            _to_numeric(params.get("collateral_value"))
            or _to_numeric(params.get("property_value"))
            or _to_numeric(result.get("collateral_value"))
        )
        loan_amount = (
            _to_numeric(params.get("loan_amount"))
            or _to_numeric(params.get("principal"))
            or _to_numeric(result.get("loan_amount"))
        )
        detail_parts: list[str] = []
        if collateral is not None:
            collateral_str = _format_currency(collateral)
            detail_parts.append(f"담보 {collateral_str}")
            maybe_highlight = _highlight("담보 가치", collateral_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        if loan_amount is not None:
            loan_str = _format_currency(loan_amount)
            detail_parts.append(f"대출 {loan_str}")
            maybe_highlight = _highlight("대출 금액", loan_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        text = f"LTV는 약 {_format_percent(percent_value)}입니다."
        if detail_parts:
            text = f"{text} ({', '.join(detail_parts)})"
        return {
            "text": text,
            "value": round(percent_value, 2),
            "unit": "percent",
            "highlights": highlights or None,
        }

    if calc_type is CalcType.DTI:
        ratio = _to_numeric(result.get("dti")) or _to_numeric(result.get("ratio"))
        if ratio is None:
            return None
        percent_value = ratio * 100.0
        income = _to_numeric(params.get("annual_income") or result.get("annual_income"))
        debt_payment = _to_numeric(params.get("total_debt_payment") or result.get("total_debt_payment"))
        detail_parts: list[str] = []
        if income is not None:
            income_str = _format_currency(income)
            detail_parts.append(f"연소득 {income_str}")
            maybe_highlight = _highlight("연소득", income_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        if debt_payment is not None:
            debt_str = _format_currency(debt_payment)
            detail_parts.append(f"부채 상환 {debt_str}")
            maybe_highlight = _highlight("연간 부채 상환", debt_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        text = f"DTI는 약 {_format_percent(percent_value)}입니다."
        if detail_parts:
            text = f"{text} ({', '.join(detail_parts)})"
        return {
            "text": text,
            "value": round(percent_value, 2),
            "unit": "percent",
            "highlights": highlights or None,
        }

    if calc_type is CalcType.DSR:
        ratio = _to_numeric(result.get("dsr")) or _to_numeric(result.get("ratio"))
        if ratio is None:
            return None
        percent_value = ratio * 100.0
        income = _to_numeric(params.get("annual_income") or result.get("annual_income"))
        debt_service = _to_numeric(params.get("annual_debt_service") or result.get("annual_debt_service"))
        detail_parts: list[str] = []
        if income is not None:
            income_str = _format_currency(income)
            detail_parts.append(f"연소득 {income_str}")
            maybe_highlight = _highlight("연소득", income_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        if debt_service is not None:
            debt_str = _format_currency(debt_service)
            detail_parts.append(f"원리금 상환 {debt_str}")
            maybe_highlight = _highlight("연간 원리금 상환", debt_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        text = f"DSR은 약 {_format_percent(percent_value)}입니다."
        if detail_parts:
            text = f"{text} ({', '.join(detail_parts)})"
        return {
            "text": text,
            "value": round(percent_value, 2),
            "unit": "percent",
            "highlights": highlights or None,
        }

    if calc_type is CalcType.AMORTIZATION:
        monthly_payment = _to_numeric(result.get("monthly_payment"))
        schedule = result.get("schedule")
        if monthly_payment is None and isinstance(schedule, list) and schedule:
            first = schedule[0]
            if isinstance(first, dict):
                monthly_payment = _to_numeric(first.get("payment"))
        if monthly_payment is None:
            return None
        principal = (
            _to_numeric(params.get("principal"))
            or _to_numeric(params.get("loan_amount"))
            or _to_numeric(result.get("principal"))
        )
        months = _to_numeric(params.get("months") or params.get("term_months") or result.get("months"))
        interest_rate = _to_numeric(params.get("interest_rate") or params.get("rate") or result.get("interest_rate"))
        detail_parts: list[str] = []
        if principal is not None:
            principal_str = _format_currency(principal)
            detail_parts.append(f"원금 {principal_str}")
            maybe_highlight = _highlight("대출 원금", principal_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        if months is not None:
            months_str = f"{int(round(months))}개월"
            detail_parts.append(f"기간 {months_str}")
            maybe_highlight = _highlight("상환 기간", months_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        if interest_rate is not None:
            rate_str = _format_rate(interest_rate)
            detail_parts.append(f"금리 {rate_str}")
            maybe_highlight = _highlight("연 이자율", rate_str)
            if maybe_highlight:
                highlights.append(maybe_highlight)
        text = f"월 예상 상환액은 약 {_format_currency(monthly_payment)}입니다."
        if detail_parts:
            text = f"{text} ({', '.join(detail_parts)})"
        return {
            "text": text,
            "value": int(round(monthly_payment)),
            "unit": "krw",
            "highlights": highlights or None,
        }

    if calc_type is CalcType.PAYMENT_SENSITIVITY:
        sensitivity = result.get("sensitivity")
        if not isinstance(sensitivity, list) or not sensitivity:
            return None
        items = [
            item
            for item in sensitivity
            if isinstance(item, dict) and _to_numeric(item.get("interest_rate")) is not None
        ]
        if not items:
            return None
        items.sort(key=lambda item: _to_numeric(item.get("interest_rate")) or 0.0)
        best = items[0]
        best_rate = _to_numeric(best.get("interest_rate")) or 0.0
        best_payment = _to_numeric(best.get("monthly_payment"))
        if best_payment is None:
            return None
        text = f"금리 {_format_rate(best_rate)}에서 월 납입액은 {_format_currency(best_payment)}입니다."
        if len(items) > 1:
            worst = items[-1]
            worst_rate = _to_numeric(worst.get("interest_rate")) or best_rate
            worst_payment = _to_numeric(worst.get("monthly_payment"))
            if worst_payment is not None:
                text = (
                    f"{text} 금리가 {_format_rate(worst_rate)}까지 오르면 "
                    f"{_format_currency(worst_payment)} 수준으로 늘어납니다."
                )
        highlights.extend(
            filter(
                None,
                [
                    _highlight("최저 금리 월 납입액", _format_currency(best_payment)),
                    _highlight("최저 금리", _format_rate(best_rate)),
                ],
            )
        )
        if len(items) > 1:
            worst_rate = _to_numeric(items[-1].get("interest_rate"))
            worst_payment = _to_numeric(items[-1].get("monthly_payment"))
            highlights.extend(
                filter(
                    None,
                    [
                        _highlight(
                            "최고 금리 월 납입액",
                            _format_currency(worst_payment) if worst_payment is not None else None,
                        ),
                        _highlight(
                            "최고 금리",
                            _format_rate(worst_rate) if worst_rate is not None else None,
                        ),
                    ],
                )
            )
        return {
            "text": text,
            "value": int(round(best_payment)),
            "unit": "krw",
            "highlights": highlights or None,
        }

    return None


def _is_housing_related(message: str, category: str | None) -> bool:
    """주택담보대출 도메인과 무관한 문의를 걸러낸다."""

    normalized = (message or "").lower()
    keywords = {
        "mortgage",
        "mortgages",
        "mortgage loan",
        "mortgage refinance",
        "mortgage refinancing",
        "home loan",
        "home loans",
        "home equity loan",
        "home equity line",
        "housing loan",
        "housing loans",
        "housing finance",
        "loan",
        "loans",
        "loan limit",
        "loan eligibility",
        "credit line",
        "line of credit",
        "credit score",
        "debt consolidation",
        "housing",
        "house",
        "residential",
        "primary residence",
        "second home",
        "investment property",
        "apartment",
        "villa",
        "condo",
        "condominium",
        "townhouse",
        "real estate",
        "ltv",
        "loan-to-value",
        "dti",
        "dsr",
        "gdsr",
        "interest",
        "interest rate",
        "floating rate",
        "fixed rate",
        "apr",
        "prime rate",
        "reference rate",
        "principal",
        "installment",
        "payment",
        "monthly payment",
        "weekly payment",
        "repayment",
        "amortization",
        "amortization schedule",
        "balloon payment",
        "bridge loan",
        "construction loan",
        "refinance",
        "refinancing",
        "equity",
        "home equity",
        "cash-out",
        "deposit loan",
        "reverse mortgage",
        "전세",
        "월세",
        "전세자금",
        "전세대출",
        "주택담보대출",
        "주담대",
        "담보",
        "담보대출",
        "주택",
        "부동산",
        "아파트",
        "빌라",
        "오피스텔",
        "실거주",
        "거주",
        "무주택",
        "1주택",
        "다주택",
        "보금자리",
        "디딤돌",
        "신혼희망타운",
        "청년전용",
        "특례보금자리",
        "생애최초",
        "실수요자",
        "금리",
        "이자",
        "상환",
        "원리금",
        "한도",
        "대환",
        "채무",
        "부채",
        "주택금융",
        "주택자금",
        "담보설정",
        "LTV",
        "DTI",
        "DSR",
        "총부채",
        "총원리금",
        "상환비율",
        "규제지역",
        "투기과열지구",
        "조정대상지역",
        "구입자금",
        "건축자금",
        "주거래은행",
        "중도상환수수료",
        "상환유예",
        "금융위원회",
        "금융감독원",
    }
    if any(keyword in normalized for keyword in keywords):
        return True

    if category:
        category_hint = category.lower()
        if any(keyword in category_hint for keyword in keywords):
            return True

    return False


def _resolve_websearch_config(config: WebSearchConfig) -> WebSearchConfig | None:
    headers, missing_headers = _substitute_env_tokens(config.provider.headers)
    params, missing_params = _substitute_env_tokens(config.provider.params)
    missing = missing_headers.union(missing_params)
    if missing:
        raise ValueError(f"웹 검색 자격 증명이 없습니다: {', '.join(sorted(missing))}")
    provider = replace(config.provider, headers=headers, params=params)
    return replace(config, provider=provider)


def _substitute_env_tokens(values: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    resolved: dict[str, Any] = {}
    missing: set[str] = set()

    for key, value in values.items():
        if isinstance(value, str) and "${" in value:
            def _replace(match: re.Match[str]) -> str:
                env_key = match.group(1).strip()
                env_val = os.getenv(env_key)
                if env_val is None:
                    missing.add(env_key)
                    return ""
                return env_val

            resolved_value = ENV_TOKEN_PATTERN.sub(_replace, value)
            resolved[key] = resolved_value
        else:
            resolved[key] = value

    for key, value in resolved.items():
        if isinstance(value, str) and "${" in value:
            for token in ENV_TOKEN_PATTERN.findall(value):
                missing.add(token.strip())

    return resolved, missing


def _ensure_env_loaded() -> None:
    """Ensure .env variables are loaded once for worker processes."""

    global _ENV_LOADED
    if _ENV_LOADED:
        return

    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001
        _ENV_LOADED = True
        return

    try:
        load_dotenv(override=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug(".env load skipped: %s", exc)
    finally:
        _ENV_LOADED = True


def _normalize_calc_category_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in CALC_CATEGORY_MAP:
        return normalized
    try:
        calc_type = CalcType(normalized)
    except ValueError:
        return None
    for key, mapped in CALC_CATEGORY_MAP.items():
        if mapped == calc_type:
            return key
    return None


def _infer_calc_category(
    request: ChatRequest,
    resolution: IntentResolution,
    params: dict[str, Any] | None,
) -> str | None:
    # explicit hints from raw params take precedence
    raw_params = request.params if isinstance(request.params, dict) else {}
    if raw_params:
        calc_type_hint = _normalize_calc_category_token(raw_params.get("calc_type"))
        if calc_type_hint:
            return calc_type_hint
        category_hint = _normalize_calc_category_token(raw_params.get("category"))
        if category_hint:
            return category_hint

    combined: dict[str, Any] = {}
    if params:
        combined.update(params)

    slots = resolution.slots or {}
    for key, value in slots.items():
        combined.setdefault(key, value)

    if _has_values(combined, "collateral_value") and (
        _has_values(combined, "loan_amount") or _has_values(combined, "principal")
    ):
        return "ltv"
    if _has_values(combined, "annual_income", "total_debt_payment"):
        return "dti"
    if _has_values(combined, "annual_income", "annual_debt_service"):
        return "dsr"
    if _has_values(combined, "principal") and _has_non_empty_sequence(combined.get("interest_rates")):
        return "payment_sensitivity"
    if _has_values(combined, "loan_amount") and _has_non_empty_sequence(combined.get("interest_rates")):
        return "payment_sensitivity"
    if (
        _has_values(combined, "principal", "interest_rate", "months")
        or _has_values(combined, "loan_amount", "interest_rate", "term_months")
        or _has_values(combined, "loan_amount", "interest_rate", "months")
    ):
        return "monthly_payment"

    message = (request.message or "").lower()
    ltv_keywords = ("ltv", "담보비율", "담보 비율", "담보인정비율", "담보 인정 비율", "엘티비")
    dti_keywords = ("dti", "총부채상환비율", "총 부채 상환 비율", "디티아이")
    dsr_keywords = ("dsr", "총부채원리금상환비율", "총 부채 원리금 상환 비율", "디에스알")
    monthly_keywords = (
        "월 상환",
        "월납입",
        "월 납입",
        "상환 금액",
        "상환금액",
        "월 부담",
        "월 이자",
        "원리금",
        "대출 한도",
        "한도 계산",
        "상환 계산",
    )
    sensitivity_keywords = ("민감도", "금리 변화", "payment sensitivity", "금리 민감도")

    if any(keyword in message for keyword in ltv_keywords):
        return "ltv"
    if any(keyword in message for keyword in dti_keywords):
        return "dti"
    if any(keyword in message for keyword in dsr_keywords):
        return "dsr"
    if any(keyword in message for keyword in sensitivity_keywords):
        return "payment_sensitivity"
    if any(keyword in message for keyword in monthly_keywords):
        return "monthly_payment"
    return None


def _has_non_empty_sequence(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return False


def _coerce_int(value: Any) -> Any:
    try:
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            if cleaned.endswith("개월"):
                cleaned = cleaned[: -len("개월")].strip()
            return int(cleaned)
        return int(value)
    except (TypeError, ValueError):
        return value


def _coerce_float(value: Any) -> Any:
    try:
        if isinstance(value, str):
            cleaned = value.replace("%", "").strip()
            return float(cleaned)
        return float(value)
    except (TypeError, ValueError):
        return value


def _to_numeric(value: Any) -> float | None:
    """값을 float로 변환할 수 있으면 반환하고, 불가하면 None을 돌려준다."""

    coerced_int = _coerce_int(value)
    if isinstance(coerced_int, int):
        return float(coerced_int)
    coerced_float = _coerce_float(value)
    if isinstance(coerced_float, float):
        return coerced_float
    return None


def _format_currency(value: float) -> str:
    return f"{int(round(float(value))):,}원"


def _format_percent(value: float, *, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}%"


def _format_rate(value: float, *, decimals: int = 2) -> str:
    return f"{float(value):.{decimals}f}%"


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _has_values(mapping: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if key not in mapping:
            return False
        value = mapping[key]
        if _is_empty_value(value):
            return False
    return True


def _is_missing_param(params: dict[str, Any], key: str) -> bool:
    if key not in params:
        return True
    return _is_empty_value(params[key])
