"""JSONL 기반 DAO 구현."""

from __future__ import annotations

from pathlib import Path

from .dao import ChatLog, ChatLogDAO


class JSONLChatLogDAO(ChatLogDAO):
    """TODO: 파일 기반 영속 DAO를 작성하세요."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, record: ChatLog) -> None:
        """TODO: JSONL 파일에 append 하세요."""
        raise NotImplementedError("save 메서드를 구현하세요.")

    def list_recent(self, session_id: str, *, limit: int = 20) -> list[ChatLog]:
        """TODO: 파일을 읽어 세션별 최신 로그를 반환하세요."""
        raise NotImplementedError("list_recent 메서드를 구현하세요.")
