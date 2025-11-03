"""웹 검색 설정 로더."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path("config/websearch.yaml")
_DEFAULT_WHITELIST_PATH = Path("src/websearch/whitelist.yaml")

logger = logging.getLogger(__name__)


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("${") and text.endswith("}" ):
            env_key = text[2:-1].strip()
            if not env_key:
                return ""
            env_value = os.getenv(env_key)
            if env_value is None:
                logger.warning("환경변수 %s 를 찾을 수 없습니다.", env_key)
                return ""
            return env_value
        return text
    if isinstance(value, dict):
        return {key: _resolve_env(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    return value


@dataclass(frozen=True)
class CacheConfig:
    directory: Path
    ttl_seconds: int


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    method: str
    query_param: str | None
    payload: str
    params: dict[str, Any]
    headers: dict[str, str]
    timeout: float
    max_results: int
    response_items_path: tuple[str, ...]
    response_title_field: str
    response_url_field: str
    response_snippet_field: str | None


@dataclass(frozen=True)
class WebSearchConfig:
    cache: CacheConfig
    provider: ProviderConfig
    whitelist_path: Path = _DEFAULT_WHITELIST_PATH

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "WebSearchConfig":
        cache_payload = payload.get("cache", {})
        provider_payload = payload.get("provider", {})

        cache = CacheConfig(
            directory=Path(cache_payload.get("directory", "data/web_cache")),
            ttl_seconds=int(cache_payload.get("ttl_seconds", 86_400)),
        )
        base_url_raw = provider_payload.get("base_url", "https://api.example.com/search")
        method = str(provider_payload.get("method", "GET")).upper()
        query_param = provider_payload.get("query_param")
        payload_mode = str(provider_payload.get("payload", "params")).lower()
        params = _resolve_env(provider_payload.get("params", {}))
        headers_resolved = _resolve_env(provider_payload.get("headers", {}))
        headers = {str(key): str(value) for key, value in headers_resolved.items()}

        response_payload = provider_payload.get("response", {})
        items_path_raw = response_payload.get("items_path", [])
        if isinstance(items_path_raw, str):
            items_path = tuple(part for part in items_path_raw.split(".") if part)
        else:
            items_path = tuple(str(part) for part in items_path_raw)
        provider = ProviderConfig(
            base_url=str(_resolve_env(base_url_raw)),
            method=method,
            query_param=str(query_param) if query_param is not None else None,
            payload=payload_mode,
            params=params if isinstance(params, dict) else {},
            headers=headers,
            timeout=float(provider_payload.get("timeout", 8)),
            max_results=int(provider_payload.get("max_results", 5)),
            response_items_path=items_path,
            response_title_field=str(response_payload.get("title_field", "title")),
            response_url_field=str(response_payload.get("url_field", "url")),
            response_snippet_field=(
                str(response_payload.get("snippet_field"))
                if response_payload.get("snippet_field") is not None
                else None
            ),
        )
        lookup = payload.get("whitelist_path")
        whitelist_path = Path(lookup) if lookup else _DEFAULT_WHITELIST_PATH
        return cls(cache=cache, provider=provider, whitelist_path=whitelist_path)


def load_websearch_config(path: Path | str | None = None) -> WebSearchConfig:
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"websearch 설정 파일을 찾을 수 없습니다: {config_path}")

    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    return WebSearchConfig.from_mapping(payload)


__all__ = [
    "CacheConfig",
    "ProviderConfig",
    "WebSearchConfig",
    "load_websearch_config",
]
