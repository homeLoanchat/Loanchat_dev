from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.websearch.config import CacheConfig, ProviderConfig, WebSearchConfig
from src.websearch.provider import RequestsSearchProvider
from src.websearch.search import search_web


@pytest.fixture()
def whitelist_file(tmp_path: Path) -> Path:
    path = tmp_path / "whitelist.yaml"
    path.write_text("domains:\n  - domain: example.com\n")
    return path


def make_config(
    tmp_path: Path,
    whitelist: Path,
    ttl: int = 3600,
    items_path: tuple[str, ...] = (),
) -> WebSearchConfig:
    cache = CacheConfig(directory=tmp_path, ttl_seconds=ttl)
    provider = ProviderConfig(
        base_url="https://api.example.com/search",
        method="GET",
        query_param="q",
        payload="params",
        params={},
        headers={},
        timeout=2.0,
        max_results=5,
        response_items_path=items_path,
        response_title_field="title",
        response_url_field="url",
        response_snippet_field="snippet",
    )
    return WebSearchConfig(cache=cache, provider=provider, whitelist_path=whitelist)


def test_search_cache_hits_within_ttl(tmp_path: Path, whitelist_file: Path) -> None:
    config = make_config(tmp_path, whitelist_file, items_path=("data", "results"))
    calls: list[str] = []

    def provider(*, query: str, max_results: int) -> list[dict[str, Any]]:
        calls.append(query)
        return [
            {
                "title": "Example",
                "url": "https://example.com/article",
                "snippet": "snippet",
            }
        ]

    results_first = search_web("대출", provider=provider, config=config)
    results_second = search_web("대출", provider=provider, config=config)

    assert len(results_first) == 1
    assert results_second == results_first
    assert len(calls) == 1, "캐시 재사용 시 provider가 재호출되지 않아야 합니다."


def test_search_cache_expires(tmp_path: Path, whitelist_file: Path) -> None:
    config = make_config(tmp_path, whitelist_file, ttl=0)
    calls: list[str] = []

    def provider(*, query: str, max_results: int) -> list[dict[str, Any]]:
        calls.append(query)
        return [
            {
                "title": "Example",
                "url": "https://example.com/article",
                "snippet": "snippet",
            }
        ]

    search_web("금리", provider=provider, config=config)
    search_web("금리", provider=provider, config=config)

    assert len(calls) == 2, "TTL이 만료되면 provider가 다시 호출되어야 합니다."


def test_whitelist_filters_results(tmp_path: Path) -> None:
    whitelist = tmp_path / "whitelist.yaml"
    whitelist.write_text(
        "domains:\n  - domain: example.com\n    paths:\n      - /allowed\n"
    )
    config = make_config(tmp_path, whitelist)

    def provider(*, query: str, max_results: int) -> list[dict[str, Any]]:
        return [
            {"title": "allow", "url": "https://example.com/allowed/1", "snippet": "ok"},
            {"title": "deny", "url": "https://example.com/other/2", "snippet": "no"},
            {"title": "deny-domain", "url": "https://bad.com/news", "snippet": "bad"},
        ]

    results = search_web("테스트", provider=provider, config=config)
    assert len(results) == 1
    assert results[0]["url"].startswith("https://example.com/allowed")


def test_requests_provider_maps_response(tmp_path: Path, whitelist_file: Path) -> None:
    config = make_config(tmp_path, whitelist_file, items_path=("data", "results"))

    provider = RequestsSearchProvider(config.provider)

    class DummyResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

        def raise_for_status(self) -> None:
            return None

    class DummySession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def request(self, method: str, url: str, **kwargs: Any) -> DummyResponse:
            self.calls.append({"method": method, "url": url, **kwargs})
            payload = {
                "data": {
                    "results": [
                        {
                            "title": "Example Title",
                            "url": "https://example.com/allowed/123",
                            "snippet": "Example snippet",
                        }
                    ]
                }
            }
            return DummyResponse(payload)

    dummy_session = DummySession()
    provider.session = dummy_session  # type: ignore[assignment]

    results = provider(query="테스트", max_results=3)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/allowed/123"
    assert dummy_session.calls, "요청이 발생해야 합니다."
