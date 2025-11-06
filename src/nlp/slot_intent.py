"""의도/슬롯 추출 모듈."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)

_CALC_KEYWORDS = {
    "얼마",
    "한도",
    "가능",
    "계산",
    "원리금",
    "상환",
    "dti",
    "dsr",
    "ltv",
    "금리",
    "이자",
    "대출",
}
_STRONG_CALC_KEYWORDS = {
    "얼마",
    "한도",
    "계산",
    "원리금",
    "상환",
    "ltv",
    "dti",
    "dsr",
}
_INFO_KEYWORDS = {
    "무엇",
    "설명",
    "정의",
    "이란",
    "조건",
    "요건",
    "필요",
    "절차",
    "방법",
    "가능한가",
    "알려줘",
}
_QUESTION_TOKENS = {"?", "어떻게", "왜", "언제", "어디", "무엇"}

_AMOUNT_PATTERN = re.compile(r"(?P<num>\d[\d,\.]*)\s*(?P<unit>억|만|천|백)?\s*(?P<currency>원|만원|억원)?")
_RATE_PATTERN = re.compile(r"(?P<rate>\d+(?:\.\d+)?)\s*%")
_TERM_YEAR_PATTERN = re.compile(r"(?P<years>\d+)\s*년")
_TERM_MONTH_PATTERN = re.compile(r"(?P<months>\d+)\s*개월?")


class LLMClient(Protocol):
    """LLM 보조 호출용 최소 인터페이스."""

    def invoke(self, prompt: str, *, temperature: float = 0.0) -> str:
        ...


@dataclass
class RuleAnalysis:
    intent: str
    slots: Dict[str, Any]
    confidence: Dict[str, Any]


def extract_intent_and_slots(message: str) -> dict[str, object]:
    """규칙 기반 분석 + (선택적) LLM 보조 결과를 반환한다."""

    message = (message or "").strip()
    if not message:
        return {
            "intent": "info",
            "slots": {},
            "confidence": {"score": 0.0, "source": "empty", "signals": {}},
        }

    rule = _rule_based_analysis(message)
    llm = _call_llm_router(message, rule)
    merged = _merge_results(rule, llm)
    return merged


def _rule_based_analysis(message: str) -> RuleAnalysis:
    lowered = message.lower()
    tokens = set(lowered.split())
    has_number = bool(re.search(r"\d", message))

    calc_hits = sum(1 for kw in _CALC_KEYWORDS if kw in lowered)
    info_hits = sum(1 for kw in _INFO_KEYWORDS if kw in lowered)
    question_hits = sum(1 for kw in _QUESTION_TOKENS if kw in lowered or kw in tokens)
    has_strong_calc_keyword = any(kw in lowered for kw in _STRONG_CALC_KEYWORDS)

    slots = _extract_slots(message)

    calc_condition = False
    if calc_hits and has_number:
        calc_condition = True
    elif calc_hits > info_hits:
        if has_number or has_strong_calc_keyword or calc_hits >= 2:
            calc_condition = True

    if calc_condition:
        intent = "calc"
        base = 0.55 + min(calc_hits, 3) * 0.1
        if has_number:
            base += 0.1
        if slots:
            base += 0.05
    else:
        intent = "info"
        base = 0.5 + min(info_hits, 2) * 0.1
        if question_hits:
            base += 0.05
        if not has_number:
            base += 0.05

    score = max(0.0, min(base, 0.92))

    confidence = {
        "score": round(score, 3),
        "source": "rule",
        "signals": {
            "calc_hits": calc_hits,
            "info_hits": info_hits,
            "question_hits": question_hits,
            "has_number": has_number,
            "slot_count": len(slots),
        },
    }

    return RuleAnalysis(intent=intent, slots=slots, confidence=confidence)


def _extract_slots(message: str) -> Dict[str, Any]:
    slots: Dict[str, Any] = {}

    for match in _AMOUNT_PATTERN.finditer(message):
        raw = match.group("num")
        unit = match.group("unit")
        currency = match.group("currency")
        if not raw:
            continue
        try:
            normalized = _normalize_amount(raw, unit, currency)
        except ValueError:
            continue
        if not normalized:
            continue
        if "loan_amount" not in slots:
            slots["loan_amount"] = normalized
        else:
            slots.setdefault("additional_amounts", []).append(normalized)
        if currency and "currency" not in slots:
            slots["currency"] = currency

    rate_match = _RATE_PATTERN.search(message)
    if rate_match:
        try:
            slots["interest_rate"] = float(rate_match.group("rate"))
        except (TypeError, ValueError):
            pass

    years_match = _TERM_YEAR_PATTERN.search(message)
    months_match = _TERM_MONTH_PATTERN.search(message)
    term_months: Optional[int] = None
    if years_match:
        term_months = int(years_match.group("years")) * 12
    if months_match:
        term_months = (term_months or 0) + int(months_match.group("months"))
    if term_months:
        slots["term_months"] = term_months

    return slots


def _normalize_amount(raw: str, unit: Optional[str], currency: Optional[str] = None) -> Optional[int]:
    cleaned = raw.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError as exc:  # noqa: BLE001
        raise ValueError from exc

    multiplier = 1.0
    if unit == "억":
        multiplier = 100_000_000.0
    elif unit == "만":
        multiplier = 10_000.0
    elif unit == "천":
        multiplier = 1_000.0
    elif unit == "백":
        multiplier = 100.0
    elif not unit and currency in {"만원"}:
        multiplier = 10_000.0
    elif not unit and currency in {"억원"}:
        multiplier = 100_000_000.0

    normalized = int(value * multiplier)
    return normalized if normalized > 0 else None


def _call_llm_router(message: str, rule: RuleAnalysis) -> Optional[dict[str, Any]]:
    client = _load_llm_client()
    if not client:
        return None

    prompt = _build_llm_prompt(message, rule)
    try:
        raw = client.invoke(prompt, temperature=0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM router 호출 실패: %s", exc)
        return None

    parsed = _parse_llm_response(raw)
    return parsed


def _load_llm_client() -> Optional[LLMClient]:
    try:
        from src.llm.client import get_router_client  # type: ignore
    except ImportError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM router client 초기화 실패: %s", exc)
        return None

    try:
        client = get_router_client()  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM router client 인스턴스 생성 실패: %s", exc)
        return None
    return client


def _build_llm_prompt(message: str, rule: RuleAnalysis) -> str:
    return (
        "당신은 금융 상담 챗봇의 라우터입니다.\n"
        "사용자 발화의 intent(calc/info)와 핵심 슬롯(loan_amount, interest_rate, term_months 등)을 JSON으로 추출하세요.\n"
        "가능하면 아래 규칙 기반 결과를 참고하되, 확신이 없으면 score를 0.5 이하로 설정합니다.\n"
        "응답 예시: {\"intent\": \"calc\", \"slots\": {\"loan_amount\": 300000000}, \"confidence\": {\"score\": 0.82}}\n"
        f"규칙 기반 intent: {rule.intent}\n"
        f"규칙 기반 confidence: {rule.confidence}\n"
        f"사용자 발화: {message}\n"
    )


def _parse_llm_response(raw: str) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        logger.debug("LLM 응답이 JSON 포맷이 아님: %s", raw)
        return None

    intent = data.get("intent")
    slots = data.get("slots") or {}
    confidence = data.get("confidence") or {}

    if not isinstance(slots, dict):
        slots = {}
    if not isinstance(confidence, dict):
        confidence = {}

    result = {
        "intent": intent if isinstance(intent, str) else None,
        "slots": slots,
        "confidence": confidence,
    }
    return result


def _merge_results(rule: RuleAnalysis, llm: Optional[dict[str, Any]]) -> dict[str, Any]:
    final_intent = rule.intent
    final_slots = dict(rule.slots)
    final_confidence = dict(rule.confidence)
    final_confidence["source"] = "rule"

    if not llm:
        return {
            "intent": final_intent,
            "slots": final_slots,
            "confidence": final_confidence,
        }

    llm_intent = llm.get("intent")
    llm_slots = llm.get("slots") or {}
    llm_conf = llm.get("confidence") or {}
    if isinstance(llm_slots, dict):
        final_slots.update({k: v for k, v in llm_slots.items() if v is not None})

    rule_score = float(rule.confidence.get("score") or 0.0)
    llm_score = float(llm_conf.get("score") or 0.0)

    if isinstance(llm_intent, str):
        if llm_intent == rule.intent:
            final_intent = rule.intent
            blended = min(0.99, (rule_score * 0.6) + (llm_score * 0.4) + 0.05)
            final_confidence["score"] = round(max(rule_score, blended), 3)
            final_confidence["source"] = "hybrid"
        elif llm_score >= rule_score + 0.15:
            final_intent = llm_intent
            final_confidence["score"] = round(min(0.95, llm_score), 3)
            final_confidence["source"] = "llm_override"
            final_confidence["reason"] = "llm_override"
        else:
            final_confidence["score"] = round(rule_score, 3)
            final_confidence["source"] = "rule_preferred"
    else:
        final_confidence["score"] = round(rule_score, 3)

    final_confidence["llm_score"] = round(llm_score, 3)
    final_confidence["rule_score"] = round(rule_score, 3)

    return {
        "intent": final_intent,
        "slots": final_slots,
        "confidence": final_confidence,
    }


__all__ = ["extract_intent_and_slots"]
