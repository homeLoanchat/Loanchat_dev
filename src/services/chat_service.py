"""Chat 서비스 계층."""

from __future__ import annotations

from dataclasses import dataclass
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
            if request.category and request.category not in CALCULATIONAL_CATEGORIES:
                raise InvalidValueError(
                    "지원하지 않는 category 입니다.",
                    field="category",
                    details={"category": request.category},
                )

            params = _prepare_calc_params(request, resolution)
            if not params:
                raise InvalidValueError(
                    "계산형 intent에는 params가 필요합니다.",
                    field="params",
                )

            started = perf_counter()
            compute_payload = self._compute.run(
                category=request.category,
                params=params,
            )
            elapsed_ms = round((perf_counter() - started) * 1000.0, 3)
            compute_payload = _attach_latency(compute_payload, elapsed_ms)
            compute_payload = _attach_intent_metadata(compute_payload, resolution)
            return build_chat_response(
                intent=intent,
                category=request.category,
                data=compute_payload,
                message="계산형 답변을 생성했습니다.",
                generated_at=generated_at,
                mock=getattr(self._compute, "is_mock", False),
            )

        raise InvalidValueError("의도를 판별하지 못했습니다.", field="intent")


@lru_cache(maxsize=1)
def _get_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline()


@lru_cache(maxsize=1)
def _get_retriever() -> RetrievalRunner:
    return PipelineRetriever(pipeline=_get_retrieval_pipeline())


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
            params = dict(params or {})
            calc_type = _resolve_calc_type(category)
            required = CALC_REQUIRED_PARAMS.get(calc_type, [])
            missing = [
                key
                for key in required
                if key not in params or params[key] in (None, "")
            ]
            if missing:
                raise InvalidValueError(
                    "계산에 필요한 추가 정보가 없습니다.",
                    field="params",
                    details={
                        "missing_params": missing,
                        "calc_type": calc_type.value,
                    },
                )
            result = compute_service.calculate(calc_type=calc_type, params=params)
            return {"result": result, "calc_type": calc_type.value, "params": params}

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
    if resolution.slots:
        for key, value in resolution.slots.items():
            params.setdefault(key, value)
    return params


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


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}
