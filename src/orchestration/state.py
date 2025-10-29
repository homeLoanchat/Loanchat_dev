"""LangGraph 상태 스키마 정의."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationState:
    """TODO: 대화 이력, 요약, 검색 결과 등을 포함한 상태 필드를 정의하세요."""

    messages: list[Any] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
