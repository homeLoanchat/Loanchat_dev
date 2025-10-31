"""웹 검색 설정 로더."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path("config/websearch.yaml")
_DEFAULT_WHITELIST_PATH = Path("src/websearch/whitelist.yaml")


@dataclass(frozen=True)
class CacheConfig:
    directory: Path
    ttl_seconds: int


@dataclass(frozen=True)
class ProviderConfig:
    max_results: int


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
        provider = ProviderConfig(
            max_results=int(provider_payload.get("max_results", 5)),
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
