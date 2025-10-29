from __future__ import annotations

import pytest

from src.compute.policy import get_policy


def test_get_policy_known_product_returns_copy() -> None:
    policy = get_policy("KR", "mortgage")
    assert policy["ltv_limit"] == 0.7

    policy["ltv_limit"] = 0.2
    new_policy = get_policy("KR", "mortgage")
    assert new_policy["ltv_limit"] == 0.7


def test_get_policy_falls_back_to_default() -> None:
    policy = get_policy("kr", "unknown-product")
    assert policy["currency"] == "KRW"
    assert policy["ltv_limit"] == 0.7


def test_get_policy_invalid_region() -> None:
    with pytest.raises(ValueError):
        get_policy("mars", "mortgage")


def test_get_policy_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        get_policy("", "mortgage")
    with pytest.raises(ValueError):
        get_policy("KR", "")
