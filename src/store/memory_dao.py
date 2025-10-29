"""인메모리 DAO 구현."""

from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict

from .dao import ChatLog, ChatLogDAO


class InMemoryChatLogDAO(ChatLogDAO):
    """TODO: MVP용 인메모리 저장소를 완성하세요."""

    def __init__(self) -> None:
        self._storage: DefaultDict[str, list[ChatLog]] = defaultdict(list)

    def save(self, record: ChatLog) -> None:
        """TODO: 메모리 리스트에 레코드를 추가하세요."""
        raise NotImplementedError("save 메서드를 구현하세요.")

    def list_recent(self, session_id: str, *, limit: int = 20) -> list[ChatLog]:
        """TODO: 최근 대화 로그를 최신순으로 반환하세요."""
        raise NotImplementedError("list_recent 메서드를 구현하세요.")
