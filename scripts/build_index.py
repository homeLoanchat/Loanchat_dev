"""LoanBot 인덱스 빌더.

원천 데이터를 정제·청킹하고 결과를 JSONL로 저장한 뒤 후속 임베딩 파이프라인의
입력을 준비한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.logging import configure_logging as configure_app_logging
from src.retrieval.document_loader import Document, DocumentChunk, chunk_documents, load_documents, write_chunks
from src.retrieval.vectorstore import VectorStoreCollection, init_vectorstore, upsert_embeddings

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="원천 데이터가 위치한 디렉터리",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="정제/청킹 결과를 저장할 디렉터리",
    )
    parser.add_argument(
        "--chunk-filename",
        type=str,
        default="chunks.jsonl",
        help="청크 결과 JSONL 파일명",
    )
    parser.add_argument(
        "--document-filename",
        type=str,
        default="documents.json",
        help="문서 메타데이터를 저장할 JSON 파일명",
    )
    # 청킹 하이퍼파라미터
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=800,
        help="청크 최대 길이(문자)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=120,
        help="청크 간 겹침 길이(문자)",
    )
    parser.add_argument(
        "--min-chunk-chars",
        type=int,
        default=200,
        help="청크 최소 길이가 부족할 경우 병합을 수행할 기준",
    )
    # 백스토어 설정
    parser.add_argument(
        "--vectorstore-path",
        type=Path,
        default=Path("data/embeddings/chroma"),
        help="Chroma 퍼시스턴스 디렉터리 경로",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default="loan_documents",
        help="저장할 컬렉션명",
    )
    parser.add_argument(
        "--skip-vectorstore",
        action="store_true",
        help="임베딩 계산 및 벡터스토어 업서트를 생략",
    )
    #로깅
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="루트 로거 레벨",
    )
    return parser.parse_args()


def ensure_directory(path: Path) -> None:
    """디렉터리가 없으면 생성"""
    path.mkdir(parents=True, exist_ok=True)


def write_document_metadata(documents: Iterable[Document], output_path: Path) -> None:
    """문서 메타데이터를 JSON 파일로 저장"""
    ensure_directory(output_path.parent)
    payload: list[dict[str, object]] = []
    for document in documents:
        metadata = dict(document.metadata)
        metadata["doc_id"] = document.doc_id
        metadata.setdefault("doc_title", document.title)
        metadata.setdefault("doc_source", str(document.source_path))
        metadata.setdefault("doc_format", document.file_format)
        payload.append(metadata)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def preprocess_documents(args: argparse.Namespace) -> tuple[list[Document], list[DocumentChunk]]:
    """원천 문서를 로드하고 청킹을 수행 및 결과 반환"""
    documents = load_documents(args.raw_dir)
    if not documents:
        logger.warning("원천 디렉터리에서 문서를 찾지 못했습니다: %s", args.raw_dir)
        return [], []

    chunks = chunk_documents(
        documents,
        chunk_size=args.chunk_size,
        overlap=args.chunk_overlap,
        min_chunk_chars=args.min_chunk_chars,
    )
    logger.info("총 %d개 문서에서 %d개 청크 생성", len(documents), len(chunks))
    return documents, chunks


@dataclass(frozen=True)
class EmbeddingRecord:
    chunk_id: str
    vector: Sequence[float]
    text: str
    metadata: dict[str, object]


def embed_chunks(chunks: Sequence[DocumentChunk]) -> list[EmbeddingRecord]:
    """청크 -> 임베딩 변환"""
    records: list[EmbeddingRecord] = []
    for chunk in chunks:
        vector = hash_vector(chunk.text)
        records.append(
            EmbeddingRecord(
                chunk_id=chunk.chunk_id,
                vector=vector,
                text=chunk.text,
                metadata=chunk.metadata,
            )
        )
    logger.info("임베딩 생성 완료: %d개", len(records))
    return records


def hash_vector(value: str) -> list[float]:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return [byte / 255.0 for byte in digest]


def persist_outputs(
    documents: Iterable[Document],
    chunks: Iterable[DocumentChunk],
    *,
    output_dir: Path,
    chunk_filename: str,
    document_filename: str,
) -> None:
    """청크 결과 및 문서 메타데이터를 파일로 저장"""
    ensure_directory(output_dir)
    chunk_path = output_dir / chunk_filename
    document_path = output_dir / document_filename

    write_chunks(chunks, chunk_path)
    write_document_metadata(documents, document_path)

    logger.info("청크 JSONL 저장: %s", chunk_path)
    logger.info("문서 메타데이터 저장: %s", document_path)


def store_embeddings(
    embeddings: Sequence[EmbeddingRecord],
    *,
    vectorstore_path: Path,
    collection_name: str,
) -> None:
    """임베딩을 벡터스토어에 저장"""
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
        upsert_embeddings(collection, payload)
    finally:
        if collection is not None:
            collection.close()


def configure_logging(level: str) -> None:
    configure_app_logging()
    logging.getLogger().setLevel(level)


def main() -> None:
    """로드/정제/청킹 -> 저장 -> 임베딩 -> 벡터스토어 업서트 전체 파이프라인 실행"""
    args = parse_args()
    configure_logging(args.log_level)

    if not args.raw_dir.exists():
        raise FileNotFoundError(f"원천 데이터 디렉터리를 찾을 수 없습니다: {args.raw_dir}")

    documents, chunks = preprocess_documents(args)
    if not documents:
        return

    persist_outputs(
        documents,
        chunks,
        output_dir=args.output_dir,
        chunk_filename=args.chunk_filename,
        document_filename=args.document_filename,
    )

    if args.skip_vectorstore:
        logger.info("--skip-vectorstore 옵션으로 인해 벡터 저장을 생략합니다.")
        return

    embedding_records = embed_chunks(chunks)
    store_embeddings(
        embedding_records,
        vectorstore_path=args.vectorstore_path,
        collection_name=args.collection_name,
    )




if __name__ == "__main__":
    main()
