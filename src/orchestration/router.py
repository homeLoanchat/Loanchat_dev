"""질문 유형 라우팅 로직."""

from __future__ import annotations


def route_query(state: dict[str, object]) -> str:
    """TODO: 계산/정보/웹 검색 분기를 결정하고 다음 노드 ID를 반환하세요."""
    raise NotImplementedError("라우팅 로직을 구현하세요.")
