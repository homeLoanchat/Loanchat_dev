"""ChromaDB 기반 벡터스토어 유틸."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VectorStoreCollection:
    """ChromaDB 컬렉션 핸들."""

    client: ClientAPI
    collection: Collection

    def close(self) -> None:
        """클라이언트가 close 메서드를 지원하면 호출."""
        close_fn = getattr(self.client, "close", None)
        if callable(close_fn):
            close_fn()


def init_vectorstore(
    collection_name: str,
    *,
    persist_directory: Path | str | None = Path("data/embeddings/chroma"),
    client: ClientAPI | None = None,
    client_settings: Settings | None = None,
) -> VectorStoreCollection:
    """Chroma 컬렉션을 초기화한다.

    Args:
        collection_name: 사용할 컬렉션 이름.
        persist_directory: PersistentClient 저장 경로. None이면 EphemeralClient 사용.
        client: 외부에서 생성한 클라이언트를 주입할 때 사용.
        client_settings: 클라이언트 초기화 시 사용할 Settings.
    """

    if client is None:
        if persist_directory is None:
            logger.debug("Chroma EphemeralClient 초기화 (collection=%s)", collection_name)
            client = chromadb.EphemeralClient(settings=client_settings)
        else:
            persist_directory = Path(persist_directory)
            persist_directory.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "Chroma PersistentClient 초기화: %s (collection=%s)",
                persist_directory,
                collection_name,
            )
            client = chromadb.PersistentClient(path=str(persist_directory), settings=client_settings)
    else:
        logger.debug("주입된 Chroma 클라이언트를 사용합니다. (collection=%s)", collection_name)

    collection = client.get_or_create_collection(name=collection_name)
    return VectorStoreCollection(client=client, collection=collection)


def upsert_embeddings(
    collection: VectorStoreCollection,
    embeddings: Iterable[Mapping[str, Any]],
) -> int:
    """벡터 임베딩을 Chroma 컬렉션에 업서트한다."""

    ids: list[str] = []
    vectors: list[Sequence[float]] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for item in embeddings:
        try:
            identifier = str(item["id"])
            vector = item["vector"]
        except KeyError as exc:
            raise ValueError("id, vector 키는 필수입니다.") from exc

        if isinstance(vector, str):
            raise TypeError("vector는 문자열이 아닌 수치 시퀀스여야 합니다.")
        if not isinstance(vector, Iterable):
            raise TypeError("vector는 Iterable[float] 이어야 합니다.")

        vector_list = [float(value) for value in vector]
        text = str(item.get("text", ""))
        metadata_raw = item.get("metadata", {})
        metadata = _normalize_metadata(metadata_raw)

        ids.append(identifier)
        vectors.append(vector_list)
        documents.append(text)
        metadatas.append(metadata)

    if not ids:
        logger.info("업서트할 임베딩이 없습니다.")
        return 0

    collection.collection.upsert(
        ids=ids,
        embeddings=vectors,
        documents=documents,
        metadatas=metadatas,
    )
    logger.info("Chroma 업서트 완료: %d개", len(ids))
    return len(ids)


def _normalize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Chroma 호환 형태로 메타데이터를 정규화한다."""

    if not metadata:
        return {}

    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            normalized[str(key)] = value
        elif isinstance(value, (list, tuple)):
            normalized[str(key)] = [str(item) for item in value]
        else:
            normalized[str(key)] = str(value)
    return normalized
