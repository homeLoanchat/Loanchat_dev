"""Retriever 구현체."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from src.retrieval.pipeline import RetrievalPipeline
from src.websearch.config import WebSearchConfig, load_websearch_config
from src.websearch.search import SearchProvider, search_web

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrieverResult:
    answer: str
    sources: list[str]
    documents: list[dict[str, Any]]
    web_results: list[dict[str, Any]]
    query: str


class PipelineRetriever:
    """RetrievalPipeline + (선택) 웹 검색을 결합한 Retriever."""

    is_mock = False

    def __init__(
        self,
        pipeline: RetrievalPipeline,
        *,
        web_provider: SearchProvider | None = None,
        web_config: WebSearchConfig | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._web_provider = web_provider
        self._web_config = web_config or (load_websearch_config() if web_provider else None)

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        documents = self._pipeline.search(query)
        web_results = self._search_web(query)

        answer = _compose_answer(documents, web_results)
        sources = _collect_sources(documents, web_results)

        return {
            "answer": answer,
            "query": query,
            "category": category,
            "sources": sources,
            "documents": documents,
            "web_results": web_results,
        }

    def _search_web(self, query: str) -> list[dict[str, Any]]:
        if not self._web_provider:
            return []
        try:
            return search_web(query, provider=self._web_provider, config=self._web_config)
        except Exception as exc:  # noqa: BLE001
            logger.exception("웹 검색 실패: %s", exc)
            return []


def _collect_sources(
    documents: Iterable[dict[str, Any]],
    web_results: Iterable[dict[str, Any]],
) -> list[str]:
    sources: list[str] = []
    for item in documents:
        metadata = item.get("metadata") or {}
        doc_source = metadata.get("doc_source")
        if isinstance(doc_source, str):
            sources.append(doc_source)
    for item in web_results:
        url = item.get("url")
        if isinstance(url, str):
            sources.append(url)
    return sources


def _compose_answer(
    documents: Iterable[dict[str, Any]],
    web_results: Iterable[dict[str, Any]],
) -> str:
    docs = list(documents)
    webs = list(web_results)

    if docs:
        top_metadata = docs[0].get("metadata") or {}
        title = top_metadata.get("doc_title") or top_metadata.get("doc_name")
        count = len(docs)
        if title:
            return f"'{title}' 등 {count}건의 내부 자료를 찾았습니다."
        return f"관련 내부 자료 {count}건을 찾았습니다."

    if webs:
        first_title = webs[0].get("title") or webs[0].get("url")
        count = len(webs)
        if first_title:
            return f"외부 검색 결과 '{first_title}' 등 {count}건을 발견했습니다."
        return f"외부 검색 결과 {count}건을 발견했습니다."

    return "관련 자료를 찾지 못했습니다. 질문을 더 구체화해 주세요."


__all__ = ["PipelineRetriever", "RetrieverResult"]
