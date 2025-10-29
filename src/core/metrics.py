"""메트릭/관측성 모듈."""

from __future__ import annotations


def track_latency(name: str, *, value: float) -> None:
    """TODO: 레이턴시 측정을 기록하고 외부 모니터링(LangSmith 등)과 연동하세요."""
    raise NotImplementedError("레이턴시 트래킹을 구현하세요.")


def track_tokens(name: str, *, prompt_tokens: int, completion_tokens: int) -> None:
    """TODO: 토큰 사용량을 수집하고 스토리지 혹은 모니터링으로 전송하세요."""
    raise NotImplementedError("토큰 트래킹을 구현하세요.")
