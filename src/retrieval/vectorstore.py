"""로컬 SQLite 기반 벡터스토어 유틸.

외부 DB 없이 간단한 프로토타입을 운용하기 위한 경량 구현이다. 실제 프로덕션에서는
Pinecone, Chroma 등을 사용하는 것으로 교체할 수 있다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from typing import Mapping

logger = logging.getLogger(__name__)

# 벡터스토어 컬렉션 객체
@dataclass(slots=True)
class VectorStoreCollection:
    """SQLite 벡터스토어 핸들."""

    connection: sqlite3.Connection
    name: str

    def close(self) -> None:
        self.connection.close()

# 벡터스토어 초기화
def init_vectorstore(
    collection_name: str,
    *,
    db_path: Path | str = Path("data/embeddings/vectorstore.sqlite3"),
    pragmas: Mapping[str, str] | None = None,
) -> VectorStoreCollection:
    """로컬 SQLite 벡터스토어를 초기화한다."""

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))

    if pragmas:
        cursor = connection.cursor()
        for key, value in pragmas.items():
            cursor.execute(f"PRAGMA {key}={value}")
        cursor.close()

    # embeddings 테이블 생성    
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            collection TEXT NOT NULL,
            id TEXT NOT NULL,
            vector TEXT NOT NULL,
            text TEXT NOT NULL,
            metadata TEXT NOT NULL,
            PRIMARY KEY (collection, id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_embeddings_collection ON embeddings(collection)"
    )
    connection.commit()

    logger.debug("Vectorstore 초기화: %s (collection=%s)", db_path, collection_name)
    return VectorStoreCollection(connection=connection, name=collection_name)

# 벡터 임베딩 업서트
def upsert_embeddings(
    collection: VectorStoreCollection,
    embeddings: Iterable[Mapping[str, object]],
) -> int:
    """벡터 임베딩을 업서트한다."""

    rows: list[tuple[str, str, str, str, str]] = []
    for item in embeddings:
        try:
            identifier = str(item["id"])
            vector = item["vector"]
            text = str(item.get("text", ""))
            metadata = item.get("metadata", {})
        except KeyError as exc:
            raise ValueError("id, vector 키는 필수입니다.") from exc

        if isinstance(vector, str):
            raise TypeError("vector는 문자열이 아닌 수치 시퀀스여야 합니다.")
        if not isinstance(vector, Iterable):
            raise TypeError("vector는 Iterable[float] 이어야 합니다.")

        vector_list = [float(value) for value in vector]
        vector_json = json.dumps(vector_list)
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        rows.append((collection.name, identifier, vector_json, text, metadata_json))

    if not rows:
        logger.info("업서트할 임베딩이 없습니다.")
        return 0

    connection = collection.connection
    connection.executemany(
        """
        INSERT INTO embeddings (collection, id, vector, text, metadata)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(collection, id)
        DO UPDATE SET vector=excluded.vector,
                      text=excluded.text,
                      metadata=excluded.metadata
        """,
        rows,
    )
    connection.commit()

    logger.info("벡터스토어 업서트 완료: %d개", len(rows))
    return len(rows)
