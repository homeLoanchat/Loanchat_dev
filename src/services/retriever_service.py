"""Retriever 구현체."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Mapping

from src.retrieval.config import ConfidenceConfig
from src.retrieval.pipeline import RetrievalPipeline
from src.websearch.config import WebSearchConfig, load_websearch_config
from src.websearch.search import SearchProvider, search_web
from src.services.llm_client import ChatCompletionError, UpstageChatClient

logger = logging.getLogger(__name__)

MAX_CONTEXT_DOCUMENTS = 3
MAX_CONTEXT_WEB_RESULTS = 2
MAX_CHARS_PER_CONTEXT = 1200
DEFAULT_CHAT_MODEL = "solar-1-mini-chat"


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
            answer = _compose_answer(query, documents, web_results)
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

        payload = {
            "answer": answer,
            "query": query,
            "category": category,
            "sources": sources,
            "documents": documents,
            "web_results": web_results,
            "confidence": confidence,
        }
        return payload

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
        doc_source = metadata.get("doc_source") or metadata.get("url")
        if isinstance(doc_source, str):
            sources.append(doc_source)
    for item in web_results:
        url = item.get("url")
        if isinstance(url, str):
            sources.append(url)
    return sources


@lru_cache(maxsize=1)
def _get_chat_client() -> UpstageChatClient | None:
    # ensure .env is loaded for worker processes as well
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except Exception:  # noqa: BLE001
        pass

    api_key = os.getenv("UPSTAGE_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        logger.info("Upstage API key not configured; using template composer instead.")
        return None

    api_base = os.getenv("UPSTAGE_API_BASE") or os.getenv("LLM_API_BASE") or "https://api.upstage.ai/v1"
    model = os.getenv("UPSTAGE_CHAT_MODEL") or DEFAULT_CHAT_MODEL

    timeout = _safe_float(os.getenv("UPSTAGE_CHAT_TIMEOUT"), default=30.0)
    try:
        client = UpstageChatClient(api_key=api_key, api_base=api_base, model=model, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialise Upstage chat client: %s", exc)
        return None
    return client


def _compose_answer(
    query: str,
    documents: Iterable[dict[str, Any]],
    web_results: Iterable[dict[str, Any]],
) -> str:
    llm_client = _get_chat_client()
    if llm_client:
        try:
            return _compose_with_llm(llm_client, query, documents, web_results)
        except ChatCompletionError as exc:
            logger.warning("LLM returned unexpected payload: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to template answer due to LLM failure: %s", exc)

    return _compose_template_answer(documents, web_results)


def _compose_with_llm(
    client: UpstageChatClient,
    query: str,
    documents: Iterable[dict[str, Any]],
    web_results: Iterable[dict[str, Any]],
) -> str:
    document_context = _format_documents_for_prompt(documents)
    web_context = _format_web_results_for_prompt(web_results)
    context_sections = document_context + web_context
    context_text = "\n\n".join(context_sections) if context_sections else "자료 없음"

    system_prompt = (
        "당신은 금융 상담 전문가입니다. "
        "주어진 자료를 기반으로 한국어로 간결하고 정확한 답변을 제공합니다. "
        "추측하거나 자료에 없는 내용은 만들지 말고, 필요한 경우 추가 정보를 요청하세요. "
        "핵심 답변을 2~3문장으로 정리하고, 필요한 조건이나 주의사항이 있다면 bullet으로 정리하세요. "
        "출처 번호나 괄호 표기 없이 자연스러운 문장으로 설명합니다."
    )

    user_prompt = (
        f"[사용자 질문]\n{query.strip()}\n\n"
        "[참고 자료]\n"
        f"{context_text}\n\n"
        "위 자료만을 근거로 다음을 수행하세요:\n"
        "1. 질문에 대한 핵심 답변을 2~3문장으로 작성합니다.\n"
        "2. 추가 조건이나 주의사항이 있다면 bullet 리스트로 정리합니다.\n"
        "3. 자료에 없는 내용은 추측하지 말고, 필요한 경우 추가 정보를 요청합니다.\n"
        "4. 근거 번호, 괄호형 출처 표기 등은 사용하지 마십시오.\n"
    )

    temperature = _safe_float(os.getenv("UPSTAGE_CHAT_TEMPERATURE"), default=0.2)
    max_tokens = _safe_int(os.getenv("UPSTAGE_CHAT_MAX_TOKENS"), default=768)
    messages: list[Mapping[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return client.complete(
        messages,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


def _compose_template_answer(
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


def _format_documents_for_prompt(documents: Iterable[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for index, doc in enumerate(documents or [], start=1):
        if index > MAX_CONTEXT_DOCUMENTS:
            break
        metadata = doc.get("metadata") if isinstance(doc, dict) else {}
        title = None
        snippet_source = None
        url = None
        if isinstance(doc, dict):
            title = doc.get("title") or doc.get("name")
            snippet_source = doc.get("snippet") or doc.get("summary") or doc.get("text")
        if isinstance(metadata, dict):
            title = title or metadata.get("doc_title") or metadata.get("title") or metadata.get("doc_name")
            url = metadata.get("url") or metadata.get("doc_source") or url
            snippet_source = snippet_source or metadata.get("snippet")
        snippet = _trim_text(str(snippet_source or ""))
        if not title and snippet:
            title = snippet.split("\n", 1)[0]
        if not title and url:
            title = str(url)
        title = title or "내부 자료"
        line = f"{title}"
        if url:
            line = f"{title} ({url})"
        items.append(f"{line}\n{snippet}")
    return items


def _format_web_results_for_prompt(results: Iterable[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for index, item in enumerate(results or [], start=1):
        if index > MAX_CONTEXT_WEB_RESULTS:
            break
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or item.get("url") or "웹 자료"
        snippet = item.get("snippet") or item.get("description") or item.get("summary") or ""
        url = item.get("url")
        context = _trim_text(str(snippet))
        if url:
            items.append(f"{title} ({url})\n{context}")
        else:
            items.append(f"{title}\n{context}")
    return items


def _trim_text(text: str) -> str:
    clean = " ".join(text.split())
    if len(clean) <= MAX_CHARS_PER_CONTEXT:
        return clean
    return clean[: MAX_CHARS_PER_CONTEXT - 3] + "..."


def _safe_float(value: str | None, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _safe_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


__all__ = ["PipelineRetriever", "RetrieverResult"]
