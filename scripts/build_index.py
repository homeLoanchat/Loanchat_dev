"""LoanBot 인덱스 빌더."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings, get_settings
from src.core.logging import configure_logging as configure_app_logging
from src.retrieval.config import RetrievalConfig, load_retrieval_config
from src.retrieval.pipeline import IngestResult, RetrievalPipeline

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LoanBot 벡터 인덱스를 생성합니다.")
    parser.add_argument("--config", type=Path, default=None, help="retrieval 설정 YAML 경로")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"), help="원천 데이터 디렉터리")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="청킹 결과 저장 디렉터리",
    )
    parser.add_argument(
        "--chunk-filename",
        type=str,
        default="chunks.jsonl",
        help="청크 결과 파일명",
    )
    parser.add_argument(
        "--document-filename",
        type=str,
        default="documents.json",
        help="문서 메타데이터 파일명",
    )
    parser.add_argument("--skip-vectorstore", action="store_true", help="벡터스토어 업서트 생략")
    parser.add_argument("--log-level", type=str, default="INFO", help="루트 로그 레벨")
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    configure_app_logging()
    logging.getLogger().setLevel(level.upper())


def _merge_config(base: RetrievalConfig, settings: Settings) -> RetrievalConfig:
    vectorstore = base.vectorstore
    if settings.vectorstore_path is not None:
        vectorstore = replace(vectorstore, persist_directory=settings.vectorstore_path)
    return RetrievalConfig(chunk=base.chunk, vectorstore=vectorstore, reranker=base.reranker)


def run_build_index(
    *,
    settings: Settings | None = None,
    config_path: Optional[Path] = None,
    raw_dir: Path | None = None,
    output_dir: Path | None = None,
    chunk_filename: str = "chunks.jsonl",
    document_filename: str = "documents.json",
    skip_vectorstore: bool = False,
) -> IngestResult:
    """Retrieval 파이프라인을 실행한다."""

    cfg = settings or get_settings()
    base_config = load_retrieval_config(config_path) if config_path else load_retrieval_config()
    effective_config = _merge_config(base_config, cfg)
    pipeline = RetrievalPipeline(config=effective_config)

    result = pipeline.ingest(
        raw_dir=raw_dir or Path("data/raw"),
        output_dir=output_dir or Path("data/processed"),
        chunk_filename=chunk_filename,
        document_filename=document_filename,
        skip_vectorstore=skip_vectorstore,
    )

    if not skip_vectorstore and effective_config.vectorstore.persist_directory:
        persist_dir = effective_config.vectorstore.persist_directory
        if not persist_dir.exists():
            raise FileNotFoundError(f"벡터스토어 디렉터리가 생성되지 않았습니다: {persist_dir}")

    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        result = run_build_index(
            config_path=args.config,
            raw_dir=args.raw_dir,
            output_dir=args.output_dir,
            chunk_filename=args.chunk_filename,
            document_filename=args.document_filename,
            skip_vectorstore=args.skip_vectorstore,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("인덱스 생성 실패: %s", exc)
        return 1

    logger.info(
        "인덱스 생성 완료 - 문서 %d건, 청크 %d건, 업서트 %d건",
        len(result.documents),
        len(result.chunks),
        result.upserted,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
