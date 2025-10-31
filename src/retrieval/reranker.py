"""리랭킹 유틸."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class RerankError(RuntimeError):
    """리랭킹 처리 중 오류가 발생했을 때 사용."""


def rerank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """후보 리스트를 점수를 기준으로 정렬하고 정규화한다.

    기대하는 입력 스키마:
        - `score`: float 또는 int. 없으면 기본값 0.
        - `text`/`content` 등의 필드는 그대로 보존.
        - `metadata`: dict 라면 유지.

    외부 리랭커 연동 전까지는 단순 점수 정렬 + min/max 정규화로 대체한다.
    """

    if not candidates:
        return []

    scored: list[dict[str, Any]] = []
    for index, item in enumerate(candidates):
        score_raw = item.get("score")
        if score_raw is None:
            logger.debug("score가 없어 0으로 간주합니다. index=%d", index)
            score_value = 0.0
        else:
            try:
                score_value = float(score_raw)
            except (TypeError, ValueError) as exc:
                raise RerankError(f"score를 float으로 변환할 수 없습니다. index={index}") from exc

        enriched = dict(item)
        enriched["score"] = score_value
        scored.append(enriched)

    scored.sort(key=lambda item: item["score"], reverse=True)

    min_score, max_score = _score_range(scored)
    if max_score > min_score:
        for item in scored:
            normalized = (item["score"] - min_score) / (max_score - min_score)
            item["score_normalized"] = round(normalized, 6)
    else:
        for item in scored:
            item["score_normalized"] = 1.0 if item["score"] == max_score else 0.0

    return scored


def _score_range(items: list[dict[str, Any]]) -> tuple[float, float]:
    scores = [float(item["score"]) for item in items]
    return min(scores), max(scores)


__all__ = ["rerank", "RerankError"]
