from __future__ import annotations

from pathlib import Path

import pytest

from src.orchestration import composer
from src.orchestration.state import OrchestrationState


def test_render_answer_uses_fallback_when_template_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(composer, "PROMPTS", tmp_path)

    state = OrchestrationState(
        user_query="대출 한도가 궁금해",
        mode="info",
        sources=["https://example.com"],
    )
    state.answer = "대출 한도는 최대 3억원입니다."
    state.response_message = state.answer
    state.confidence = {"passed": True, "reason": None, "thresholds": {}}

    rendered = composer.render_answer(state)

    assert "정보 요약" in rendered
    assert "https://example.com" in rendered
    assert "충족" in rendered


def test_render_answer_custom_template(monkeypatch, tmp_path: Path) -> None:
    template = """요약 {{ summary }}\n월상환 {{ calc.repayment.monthly_payment }}"""
    (tmp_path / "composer_answer.txt").write_text(template, encoding="utf-8")

    monkeypatch.setattr(composer, "PROMPTS", tmp_path)

    state = OrchestrationState(
        user_query="한도 얼마?",
        mode="calc",
    )
    state.calc = {
        "summary": "예상 한도는 3억원입니다.",
        "repayment": {"monthly_payment": 980000, "term_months": 360},
    }
    state.response_message = state.calc["summary"]

    rendered = composer.render_answer(state)
    assert "예상 한도는 3억원입니다." in rendered
    assert "980000" in rendered
