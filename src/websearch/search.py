"""외부 웹 검색 + 캐시 모듈."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol
from urllib.parse import urlparse

import yaml

from src.websearch.config import WebSearchConfig, load_websearch_config

logger = logging.getLogger(__name__)


class SearchProvider(Protocol):
    """외부 검색 공급자의 시그니처."""

    def __call__(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class WhitelistRule:
    domain: str
    paths: tuple[str, ...]


_WHITELIST_CACHE: dict[Path, tuple[WhitelistRule, ...]] = {}


def search_web(
    query: str,
    *,
    provider: SearchProvider | None = None,
    config: WebSearchConfig | None = None,
) -> list[dict[str, Any]]:
    """화이트리스트 필터 + 디스크 캐시를 적용한 웹 검색.

    검색 공급자는 주입받는 것을 기본으로 하며, 주입되지 않으면 예외를 발생시킵니다.
    """

    if not query.strip():
        raise ValueError("query가 비어 있습니다.")

    config = config or load_websearch_config()
    cache_path = _cache_path(config, query)

    cached = _read_cache(cache_path, ttl_seconds=config.cache.ttl_seconds)
    if cached is not None:
        logger.debug("웹 검색 캐시 적중: %s", cache_path)
        return cached

    if provider is None:
        raise RuntimeError("검색 provider가 설정되지 않았습니다. search_web 호출 시 provider를 주입하세요.")

    results = provider(query=query, max_results=config.provider.max_results)
    filtered = _filter_whitelist(results, config)

    _write_cache(cache_path, query=query, results=filtered)
    return filtered


def _cache_path(config: WebSearchConfig, query: str) -> Path:
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()
    cache_dir = config.cache.directory
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{digest}.json"


def _read_cache(cache_file: Path, *, ttl_seconds: int) -> list[dict[str, Any]] | None:
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload.get("fetched_at"))
    except Exception:  # noqa: BLE001
        logger.warning("웹 검색 캐시를 읽을 수 없어 무시합니다: %s", cache_file)
        return None

    if (datetime.now(timezone.utc) - fetched_at).total_seconds() > ttl_seconds:
        logger.debug("웹 검색 캐시 만료: %s", cache_file)
        return None
    return payload.get("results", [])


def _write_cache(cache_file: Path, *, query: str, results: list[dict[str, Any]]) -> None:
    payload = {
        "query": query,
        "results": results,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _filter_whitelist(results: Iterable[dict[str, Any]], config: WebSearchConfig) -> list[dict[str, Any]]:
    rules = _load_whitelist(config.whitelist_path)
    filtered: list[dict[str, Any]] = []
    for item in results:
        url = item.get("url")
        if not isinstance(url, str):
            logger.debug("url이 없어 필터링됨: %s", item)
            continue
        if _is_allowed(url, rules):
            filtered.append(item)
        else:
            logger.debug("화이트리스트 미적합으로 제외: %s", url)
    return filtered[: config.provider.max_results]


def _load_whitelist(path: Path) -> tuple[WhitelistRule, ...]:
    cached = _WHITELIST_CACHE.get(path)
    if cached is not None:
        return cached

    if not path.exists():
        raise FileNotFoundError(f"화이트리스트 파일을 찾을 수 없습니다: {path}")

    with path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}

    rules_raw = payload.get("domains", [])
    rules: list[WhitelistRule] = []
    for entry in rules_raw:
        domain = str(entry.get("domain", "")).strip().lower()
        if not domain:
            continue
        paths = tuple(str(value) for value in entry.get("paths", []) if value)
        rules.append(WhitelistRule(domain=domain, paths=paths))
    rules_tuple = tuple(rules)
    _WHITELIST_CACHE[path] = rules_tuple
    return rules_tuple


def _is_allowed(url: str, rules: Iterable[WhitelistRule]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        logger.debug("허용되지 않는 스킴(%s): %s", parsed.scheme, url)
        return False

    host = parsed.netloc.lower()
    path = parsed.path or "/"

    for rule in rules:
        if host == rule.domain or host.endswith(f".{rule.domain}"):
            if not rule.paths:
                return True
            for prefix in rule.paths:
                if path.startswith(prefix):
                    return True
    return False


__all__ = ["SearchProvider", "search_web"]
