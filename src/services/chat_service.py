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
            params = _prepare_calc_params(request, resolution)
            inferred_category = _infer_calc_category(request, resolution)
            normalized_category = inferred_category
            calc_type: CalcType | None = None
            if normalized_category:
                calc_type = CALC_CATEGORY_MAP.get(normalized_category)

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
            compute_payload = _attach_intent_metadata(compute_payload, resolution)
            message = "계산형 답변을 생성했습니다."
            if compute_payload.get("needs_input"):
                missing = compute_payload.get("missing_params") or []
                message = _build_missing_param_message(missing, resolution)
            return build_chat_response(
                intent=intent,
                category=request.category,
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


def _build_missing_param_message(missing: list[str], resolution: IntentResolution) -> str:
    if not missing:
        return "계산 결과를 생성했습니다."
    labels = [_humanize_param_name(name) for name in missing]
    joined = ", ".join(labels)
    return f"계산을 완료하려면 다음 정보를 알려 주세요: {joined}"


def _humanize_param_name(name: str) -> str:
    return CALC_PARAM_LABELS.get(name, name)


def _infer_calc_category(request: ChatRequest, resolution: IntentResolution) -> str | None:
    # explicit hints from params take precedence
    param_dict = request.params if isinstance(request.params, dict) else {}
    if param_dict:
        calc_type_hint = param_dict.get("calc_type")
        if isinstance(calc_type_hint, str):
            normalized = calc_type_hint.strip().lower()
            if normalized in CALC_CATEGORY_MAP:
                return normalized
            try:
                calc_type = CalcType(normalized)
                for key, value in CALC_CATEGORY_MAP.items():
                    if value == calc_type:
                        return key
            except ValueError:
                pass
        category_hint = param_dict.get("category")
        if isinstance(category_hint, str):
            normalized = category_hint.strip().lower()
            if normalized in CALC_CATEGORY_MAP:
                return normalized

    if request.category and isinstance(request.category, str):
        normalized = request.category.strip().lower()
        if normalized in CALC_CATEGORY_MAP:
            return normalized

    slots = resolution.slots or {}

    def has_slots(*keys: str) -> bool:
        return all(key in slots for key in keys)

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

    if "collateral_value" in slots or "ltv" in slots:
        return "ltv"
    if has_slots("annual_income", "total_debt_payment"):
        return "dti"
    if has_slots("annual_income", "annual_debt_service"):
        return "dsr"
    if "interest_rates" in slots:
        return "payment_sensitivity"
    if any(key in slots for key in ("principal", "interest_rate", "months", "loan_amount")):
        return "monthly_payment"

    message = (request.message or "").lower()
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


def _is_missing_param(params: dict[str, Any], key: str) -> bool:
    if key not in params:
        return True
    value = params[key]
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple)) and not value:
        return True
    return False


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}
