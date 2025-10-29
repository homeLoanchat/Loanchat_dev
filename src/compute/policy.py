"""금융 상품 및 규제 정책 룰."""

from __future__ import annotations


def get_policy(region: str, product_type: str) -> dict[str, object]:
    """TODO: 지역/상품 유형별 한도, 금리, 심사 기준 등을 반환하세요."""
    raise NotImplementedError("정책 룰을 구현하세요.")
