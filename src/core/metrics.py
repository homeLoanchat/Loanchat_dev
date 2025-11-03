"""간단한 메트릭/관측성 유틸."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from statistics import median
from threading import Lock
from typing import Any

from typing_extensions import TypedDict

APP_STARTED_AT = datetime.now(timezone.utc)

_LATENCIES_MS: deque[float] = deque(maxlen=1000)
_REQUEST_COUNT = 0
_TOKEN_IN = 0
_TOKEN_OUT = 0
_LAST_REINDEX_AT: datetime | None = None
_LOCK = Lock()


class TokenUsage(TypedDict):
    prompt: int
    completion: int


def track_latency(name: str, *, value: float) -> None:  # noqa: D401
    """레이턴시(ms)를 기록한다."""

    with _LOCK:
        global _REQUEST_COUNT
        _REQUEST_COUNT += 1
        _LATENCIES_MS.append(float(value))


def track_tokens(name: str, *, prompt_tokens: int, completion_tokens: int) -> None:  # noqa: D401
    """토큰 사용량을 기록한다."""

    with _LOCK:
        global _TOKEN_IN, _TOKEN_OUT
        _TOKEN_IN += int(prompt_tokens)
        _TOKEN_OUT += int(completion_tokens)


def mark_reindex(timestamp: datetime | None = None) -> None:
    """인덱스 리프레시 시각을 기록한다."""

    with _LOCK:
        global _LAST_REINDEX_AT
        _LAST_REINDEX_AT = timestamp or datetime.now(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    k = max(min(int(round(percentile * (len(sorted_values) - 1))), len(sorted_values) - 1), 0)
    return sorted_values[k]


def collect_metrics() -> dict[str, Any]:
    """현재 메트릭 스냅샷을 반환한다."""

    with _LOCK:
        latencies = list(_LATENCIES_MS)
        request_count = _REQUEST_COUNT
        token_in = _TOKEN_IN
        token_out = _TOKEN_OUT
        last_reindex_at = _LAST_REINDEX_AT

    uptime_sec = (datetime.now(timezone.utc) - APP_STARTED_AT).total_seconds()
    p50_ms = median(latencies) if latencies else 0.0
    p95_ms = _percentile(latencies, 0.95)

    return {
        "uptime_sec": uptime_sec,
        "req_count": request_count,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "token_usage": TokenUsage(prompt=token_in, completion=token_out),
        "last_reindex_at": last_reindex_at,
    }


def reset_metrics() -> None:
    """테스트용 메트릭 초기화."""

    with _LOCK:
        global _REQUEST_COUNT, _TOKEN_IN, _TOKEN_OUT, _LAST_REINDEX_AT
        _LATENCIES_MS.clear()
        _REQUEST_COUNT = 0
        _TOKEN_IN = 0
        _TOKEN_OUT = 0
        _LAST_REINDEX_AT = None


__all__ = [
    "TokenUsage",
    "track_latency",
    "track_tokens",
    "collect_metrics",
    "mark_reindex",
    "reset_metrics",
]
