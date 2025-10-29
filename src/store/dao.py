"""스토리지 DAO 인터페이스."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ChatLog:
    """TODO: 세션 ID, 사용자 발화, 봇 응답, 메타데이터 필드를 정의하세요."""

    session_id: str
    user_message: str
    bot_response: str


class ChatLogDAO(Protocol):
    """채팅 로그 저장/조회 계약."""

    def save(self, record: ChatLog) -> None:  # noqa: D401
        """TODO: 구현체에서 영속화 로직을 작성하세요."""

    def list_recent(self, session_id: str, *, limit: int = 20) -> list[ChatLog]:  # noqa: D401
        """TODO: 최근 대화 기록을 반환하세요."""
