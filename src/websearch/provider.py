"""웹 검색 Provider 구현."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

from src.websearch.config import ProviderConfig

logger = logging.getLogger(__name__)


def _deep_get(payload: dict[str, Any], dotted: str | None) -> Any:
    if not dotted:
        return None
    current: Any = payload
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _select_items(payload: Any, items_path: tuple[str, ...]) -> list[Any]:
    current = payload
    for key in items_path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return []
    if isinstance(current, list):
        return current
    logger.debug("items_path 결과가 list가 아님: %s", current)
    return []


@dataclass
class RequestsSearchProvider:
    config: ProviderConfig
    session: requests.Session = field(default_factory=requests.Session)

    def __post_init__(self) -> None:
        if self.config.headers:
            self.session.headers.update(self.config.headers)

    def __call__(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        limit = min(max_results, self.config.max_results)
        if limit <= 0:
            return []

        params = dict(self.config.params)
        if self.config.query_param:
            params[self.config.query_param] = query

        request_kwargs: dict[str, Any] = {"timeout": self.config.timeout}
        if self.config.payload == "json":
            request_kwargs["json"] = params
        else:
            request_kwargs["params"] = params

        try:
            response = self.session.request(
                self.config.method,
                self.config.base_url,
                **request_kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("웹 검색 API 호출 실패: %s", exc)
            return []

        items = _select_items(payload, self.config.response_items_path)
        results: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _deep_get(item, self.config.response_title_field)
            url = _deep_get(item, self.config.response_url_field)
            snippet_field = self.config.response_snippet_field
            snippet = _deep_get(item, snippet_field) if snippet_field else None
            if not isinstance(url, str) or not url:
                continue
            result = {
                "title": title if isinstance(title, str) else None,
                "url": url,
                "snippet": snippet if isinstance(snippet, str) else None,
                "raw": item,
            }
            results.append(result)
            if len(results) >= limit:
                break
        return results


def create_requests_provider(config: ProviderConfig) -> RequestsSearchProvider:
    return RequestsSearchProvider(config=config)


__all__ = ["RequestsSearchProvider", "create_requests_provider"]
