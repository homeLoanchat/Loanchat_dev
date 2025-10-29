"""리랭킹 유틸."""

from __future__ import annotations


def rerank(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    """TODO: Upstage 등 외부 리랭커를 호출하고 스코어를 정규화하세요."""
    raise NotImplementedError("리랭크 로직을 구현하세요.")
