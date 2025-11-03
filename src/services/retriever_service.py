"""Retriever 구현체."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from src.retrieval.config import ConfidenceConfig
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
    confidence: dict[str, Any]


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
        self._confidence: ConfidenceConfig = pipeline.config.confidence
        self._web_provider = web_provider
        self._web_config = web_config or (load_websearch_config() if web_provider else None)

    def run(
        self,
        *,
        category: str | None,
        query: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        logger.debug("PipelineRetriever.run start category=%s query=%s", category, query)
        documents = self._pipeline.search(query)
        web_results = self._search_web(query)

        confidence = self._evaluate_confidence(documents)
        if confidence["passed"]:
            answer = _compose_answer(documents, web_results)
            sources = _collect_sources(documents, web_results)
        else:
            logger.info(
                "Retriever confidence threshold not met reason=%s top_score=%s normalized=%s hits=%s",
                confidence.get("reason"),
                confidence.get("top_score"),
                confidence.get("top_score_normalized"),
                confidence.get("hits"),
            )
            answer = "질문과 직접 일치하는 근거를 찾지 못했습니다. 추가 정보를 제공해 주시면 더 정확히 안내드릴 수 있어요."
            sources = []

        return {
            "answer": answer,
            "query": query,
            "category": category,
            "sources": sources,
            "documents": documents,
            "web_results": web_results,
            "confidence": confidence,
        }

    def _search_web(self, query: str) -> list[dict[str, Any]]:
        if not self._web_provider:
            return []
        try:
            return search_web(query, provider=self._web_provider, config=self._web_config)
        except Exception as exc:  # noqa: BLE001
            logger.exception("웹 검색 실패: %s", exc)
            return []

    def _evaluate_confidence(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        """검색 결과 기반으로 신뢰도를 계산한다."""

        thresholds = {
            "min_score": self._confidence.min_score,
            "min_score_normalized": self._confidence.min_score_normalized,
            "min_hits": self._confidence.min_hits,
        }

        if not documents:
            return {
                "passed": False,
                "reason": "no_candidates",
                "top_score": None,
                "top_score_normalized": None,
                "top_document_id": None,
                "hits": 0,
                "thresholds": thresholds,
            }

        top = documents[0] if documents else {}
        top_score = float(top.get("score") or 0.0)
        top_score_normalized = float(top.get("score_normalized") or 0.0)
        hits = len(documents)

        meets_hits = hits >= thresholds["min_hits"]
        meets_score = top_score >= thresholds["min_score"]
        meets_score_norm = top_score_normalized >= thresholds["min_score_normalized"]
        passed = all((meets_hits, meets_score, meets_score_norm))

        reasons: list[str] = []
        if not meets_hits:
            reasons.append("not_enough_hits")
        if not meets_score:
            reasons.append("score_below_threshold")
        if not meets_score_norm:
            reasons.append("normalized_score_below_threshold")

        return {
            "passed": passed,
            "reason": ",".join(reasons) if reasons else None,
            "top_score": top_score,
            "top_score_normalized": top_score_normalized,
            "top_document_id": top.get("id"),
            "hits": hits,
            "thresholds": thresholds,
        }


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
