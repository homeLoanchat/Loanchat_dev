"""LoanBot 인덱스 빌더.

원천 데이터를 정제·청킹하고 결과를 JSONL로 저장한 뒤 후속 임베딩 파이프라인의
입력을 준비한다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.logging import configure_logging as configure_app_logging
from src.retrieval.config import RetrievalConfig, load_retrieval_config
from src.retrieval.pipeline import RetrievalPipeline

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="retrieval 설정 YAML 경로 (기본값: config/retrieval.yaml)",
    )
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
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="청크 최대 길이(문자) (설정 파일 우선)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="청크 간 겹침 길이(문자) (설정 파일 우선)",
    )
    parser.add_argument(
        "--min-chunk-chars",
        type=int,
        default=None,
        help="청크 최소 길이가 부족할 경우 병합 기준 (설정 파일 우선)",
    )
    parser.add_argument(
        "--vectorstore-path",
        type=Path,
        default=None,
        help="Chroma 퍼시스턴스 디렉터리 경로 (설정 파일 우선)",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default=None,
        help="저장할 컬렉션명 (설정 파일 우선)",
    )
    parser.add_argument(
        "--skip-vectorstore",
        action="store_true",
        help="임베딩 계산 및 벡터스토어 업서트를 생략",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="루트 로거 레벨",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    configure_app_logging()
    logging.getLogger().setLevel(level)


def _merge_config(base: RetrievalConfig, args: argparse.Namespace) -> RetrievalConfig:
    chunk = base.chunk
    if args.chunk_size is not None:
        chunk = replace(chunk, size=args.chunk_size)
    if args.chunk_overlap is not None:
        chunk = replace(chunk, overlap=args.chunk_overlap)
    if args.min_chunk_chars is not None:
        chunk = replace(chunk, min_chars=args.min_chunk_chars)

    vectorstore = base.vectorstore
    if args.vectorstore_path is not None:
        vectorstore = replace(vectorstore, persist_directory=args.vectorstore_path)
    if args.collection_name is not None:
        vectorstore = replace(vectorstore, collection_name=args.collection_name)

    return RetrievalConfig(chunk=chunk, vectorstore=vectorstore, reranker=base.reranker)


def main() -> None:
    """Retrieval 파이프라인 전체를 실행한다."""
    args = parse_args()
    configure_logging(args.log_level)

    if not args.raw_dir.exists():
        raise FileNotFoundError(f"원천 데이터 디렉터리를 찾을 수 없습니다: {args.raw_dir}")

    base_config = load_retrieval_config(args.config) if args.config else load_retrieval_config()
    effective_config = _merge_config(base_config, args)
    pipeline = RetrievalPipeline(config=effective_config)

    result = pipeline.ingest(
        raw_dir=args.raw_dir,
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
