"""Retrieval 모듈 파이프라인 유틸."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.retrieval.config import RetrievalConfig, load_retrieval_config
from src.retrieval.document_loader import (
    Document,
    DocumentChunk,
    chunk_documents,
    load_documents,
    write_chunks,
)
from src.retrieval.embedding import EmbeddingClient, create_embedder
from src.retrieval.vectorstore import VectorStoreCollection, init_vectorstore, upsert_embeddings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingRecord:
    chunk_id: str
    vector: Sequence[float]
    text: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class IngestResult:
    documents: list[Document]
    chunks: list[DocumentChunk]
    upserted: int


class RetrievalPipeline:
    """문서 로딩 → 청킹 → 임베딩 저장 → 리랭킹 흐름을 조립한다."""

    def __init__(
        self,
        config: RetrievalConfig | None = None,
        *,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._config = config or load_retrieval_config()
        self._embedder = embedder or create_embedder(self._config.embedding)

    @property
    def config(self) -> RetrievalConfig:
        return self._config

    def ingest(
        self,
        *,
        raw_dir: Path,
        output_dir: Path | None = None,
        chunk_filename: str = "chunks.jsonl",
        document_filename: str = "documents.json",
        persist_outputs: bool = True,
        skip_vectorstore: bool = False,
    ) -> IngestResult:
        documents = load_documents(raw_dir)
        if not documents:
            logger.warning("원천 문서를 찾지 못했습니다: %s", raw_dir)
            return IngestResult(documents=[], chunks=[], upserted=0)

        chunk_cfg = self._config.chunk
        chunks = chunk_documents(
            documents,
            chunk_size=chunk_cfg.size,
            overlap=chunk_cfg.overlap,
            min_chunk_chars=chunk_cfg.min_chars,
        )
        logger.info("총 %d개 문서에서 %d개 청크 생성", len(documents), len(chunks))

        if persist_outputs and output_dir is not None:
            _persist_outputs(
                documents,
                chunks,
                output_dir=output_dir,
                chunk_filename=chunk_filename,
                document_filename=document_filename,
            )

        upserted = 0
        if not skip_vectorstore and chunks:
            embeddings = self._build_embedding_records(chunks)
            upserted = store_embeddings(
                embeddings,
                vectorstore_path=self._config.vectorstore.persist_directory,
                collection_name=self._config.vectorstore.collection_name,
            )
        return IngestResult(documents=documents, chunks=chunks, upserted=upserted)

    def rerank(self, candidates: list[dict[str, object]]) -> list[dict[str, object]]:
        """리랭킹 구현 상태에 따라 결과를 잘라낸다."""
        if not candidates:
            return []

        try:
            from src.retrieval import reranker

            ranked = reranker.rerank(candidates)
        except NotImplementedError:
            logger.info("reranker가 아직 구현되지 않아 원본 순서를 반환합니다.")
            ranked = candidates
        except Exception as exc:  # noqa: BLE001
            logger.exception("리랭킹 중 오류 발생, 원본 순서를 반환합니다: %s", exc)
            ranked = candidates

        top_k = self._config.reranker.top_k
        if top_k and len(ranked) > top_k:
            ranked = ranked[:top_k]
        return ranked

    def search(self, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        """쿼리 문장을 기반으로 벡터스토어에서 후보를 검색한다."""

        if not query.strip():
            logger.warning("빈 쿼리로 인해 검색을 수행하지 않습니다.")
            return []

        limit = limit or self._config.reranker.top_k or 5
        limit = max(limit, 1)

        vectors = self._embed_texts([query])
        if not vectors:
            logger.warning("임베딩 생성 실패로 검색을 중단합니다.")
            return []
        vector = vectors[0]

        collection: VectorStoreCollection | None = None
        try:
            collection = init_vectorstore(
                self._config.vectorstore.collection_name,
                persist_directory=self._config.vectorstore.persist_directory,
            )
            response = collection.collection.query(
                query_embeddings=[vector],
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("벡터스토어 조회 실패: %s", exc)
            return []
        finally:
            if collection is not None:
                collection.close()

        candidates = _build_candidates(response)
        if not candidates:
            return []
        return self.rerank(candidates)

    def _embed_texts(self, texts: Sequence[str]) -> list[Sequence[float]]:
        vectors = self._embedder.embed(texts)
        if not vectors:
            return []
        if len(vectors) != len(texts):
            raise RuntimeError("임베딩 결과 수가 입력 텍스트 수와 일치하지 않습니다.")
        return vectors

    def _build_embedding_records(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> list[EmbeddingRecord]:
        texts = [chunk.text for chunk in chunks]
        vectors = self._embed_texts(texts)
        records: list[EmbeddingRecord] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            records.append(
                EmbeddingRecord(
                    chunk_id=chunk.chunk_id,
                    vector=vector,
                    text=chunk.text,
                    metadata=chunk.metadata,
                )
            )
        validate_embedding_records(records)
        logger.info("임베딩 생성 완료: %d개", len(records))
        return records


def store_embeddings(
    embeddings: Sequence[EmbeddingRecord],
    *,
    vectorstore_path: Path,
    collection_name: str,
) -> int:
    collection: VectorStoreCollection | None = None
    try:
        collection = init_vectorstore(
            collection_name,
            persist_directory=vectorstore_path,
        )
        payload = [
            {
                "id": record.chunk_id,
                "vector": list(record.vector),
                "text": record.text,
                "metadata": record.metadata,
            }
            for record in embeddings
        ]
        validate_embedding_payload(payload)
        return upsert_embeddings(collection, payload)
    finally:
        if collection is not None:
            collection.close()


def write_document_metadata(documents: Iterable[Document], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload: list[dict[str, object]] = []
    for document in documents:
        metadata = dict(document.metadata)
        metadata["doc_id"] = document.doc_id
        metadata.setdefault("doc_title", document.title)
        metadata.setdefault("doc_source", str(document.source_path))
        metadata.setdefault("doc_format", document.file_format)
        payload.append(metadata)
    output_path.write_text(
        json_dumps(payload),
        encoding="utf-8",
    )


def _persist_outputs(
    documents: Iterable[Document],
    chunks: Iterable[DocumentChunk],
    *,
    output_dir: Path,
    chunk_filename: str,
    document_filename: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = output_dir / chunk_filename
    document_path = output_dir / document_filename
    write_chunks(chunks, chunk_path)
    write_document_metadata(documents, document_path)
    logger.info("청크 JSONL 저장: %s", chunk_path)
    logger.info("문서 메타데이터 저장: %s", document_path)


def json_dumps(payload: list[dict[str, object]]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_candidates(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Chroma query 응답으로부터 후보 리스트를 생성한다."""

    ids = _first(response.get("ids"))
    documents = _first(response.get("documents"))
    metadatas = _first(response.get("metadatas"))
    distances = _first(response.get("distances"))

    if not ids and documents:
        ids = [f"doc-{index}" for index, _ in enumerate(documents)]

    if not ids:
        return []

    results: list[dict[str, Any]] = []
    for index, identifier in enumerate(ids):
        metadata = metadatas[index] if metadatas and index < len(metadatas) else {}
        document = documents[index] if documents and index < len(documents) else ""
        distance = distances[index] if distances and index < len(distances) else None
        score = _distance_to_score(distance)
        results.append(
            {
                "id": identifier,
                "text": document,
                "metadata": metadata or {},
                "distance": distance,
                "score": score,
            }
        )
    return results


def _first(value: Any) -> list[Any] | None:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return None


def _distance_to_score(distance: Any) -> float:
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 / (1.0 + value)


def validate_embedding_records(records: Sequence[EmbeddingRecord]) -> None:
    if not records:
        raise ValueError("임베딩 레코드가 비어 있습니다.")

    vector_length: int | None = None
    for record in records:
        if not record.vector:
            raise ValueError(f"임베딩 벡터가 비어 있습니다: {record.chunk_id}")
        current_length = len(record.vector)
        if vector_length is None:
            vector_length = current_length
        elif vector_length != current_length:
            raise ValueError("임베딩 벡터 길이가 일관되지 않습니다.")
        if not record.metadata.get("chunk_id"):
            raise ValueError(
                f"chunk 메타데이터에 chunk_id가 없습니다: {record.chunk_id}",
            )


def validate_embedding_payload(payload: Sequence[dict[str, Any]]) -> None:
    for item in payload:
        vector = item.get("vector")
        if not isinstance(vector, list) or not vector:
            raise ValueError("벡터 정보가 올바르지 않습니다.")
        if any(not isinstance(value, (int, float)) for value in vector):
            raise ValueError("벡터 값은 숫자여야 합니다.")
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("메타데이터는 dict 형태여야 합니다.")
        if metadata.get("chunk_id") != item.get("id"):
            raise ValueError("chunk_id와 id가 일치하지 않습니다.")


__all__ = [
    "EmbeddingRecord",
    "IngestResult",
    "RetrievalPipeline",
    "load_retrieval_config",
    "store_embeddings",
    "validate_embedding_payload",
    "validate_embedding_records",
    "write_document_metadata",
]
