"""Retrieval 파이프라인 설정 로더."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path("config/retrieval.yaml")


@dataclass(frozen=True)
class ChunkConfig:
    size: int
    overlap: int
    min_chars: int


@dataclass(frozen=True)
class VectorStoreConfig:
    persist_directory: Path
    collection_name: str


@dataclass(frozen=True)
class RerankerConfig:
    top_k: int
    score_key: str


@dataclass(frozen=True)
class ConfidenceConfig:
    min_score: float
    min_score_normalized: float
    min_hits: int


@dataclass(frozen=True)
class RetrievalConfig:
    chunk: ChunkConfig
    vectorstore: VectorStoreConfig
    reranker: RerankerConfig
    confidence: ConfidenceConfig

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "RetrievalConfig":
        chunk_payload = payload.get("chunk", {})
        vectorstore_payload = payload.get("vectorstore", {})
        reranker_payload = payload.get("reranker", {})
        confidence_payload = payload.get("confidence", {})

        chunk = ChunkConfig(
            size=int(chunk_payload.get("size", 800)),
            overlap=int(chunk_payload.get("overlap", 120)),
            min_chars=int(chunk_payload.get("min_chars", 200)),
        )
        vectorstore = VectorStoreConfig(
            persist_directory=Path(vectorstore_payload.get("persist_directory", "data/embeddings/chroma")),
            collection_name=str(vectorstore_payload.get("collection_name", "loan_documents")),
        )
        reranker = RerankerConfig(
            top_k=int(reranker_payload.get("top_k", 5)),
            score_key=str(reranker_payload.get("score_key", "score")),
        )
        confidence = ConfidenceConfig(
            min_score=float(confidence_payload.get("min_score", 0.0)),
            min_score_normalized=float(confidence_payload.get("min_score_normalized", 0.0)),
            min_hits=int(confidence_payload.get("min_hits", 0)),
        )
        return cls(chunk=chunk, vectorstore=vectorstore, reranker=reranker, confidence=confidence)


def load_retrieval_config(path: Path | str | None = None) -> RetrievalConfig:
    """YAML 경로에서 RetrievalConfig를 로드한다."""

    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"retrieval 설정 파일을 찾을 수 없습니다: {config_path}")

    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    return RetrievalConfig.from_mapping(payload)


__all__ = [
    "ChunkConfig",
    "VectorStoreConfig",
    "RerankerConfig",
    "ConfidenceConfig",
    "RetrievalConfig",
    "load_retrieval_config",
]
