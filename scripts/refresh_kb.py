"""지식베이스 증분 업데이트 스크립트."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.logging import configure_logging as configure_app_logging
from src.retrieval.config import load_retrieval_config
from src.retrieval.pipeline import RetrievalPipeline

logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
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
        help="증분 반영할 원천 데이터 디렉터리",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="정제/청킹 결과 저장 디렉터리",
    )
    parser.add_argument(
        "--skip-vectorstore",
        action="store_true",
        help="청킹 결과만 갱신하고 벡터스토어 업서트를 생략",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="루트 로거 레벨",
    )
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    configure_app_logging()
    logging.getLogger().setLevel(level)


def run_refresh_kb(args: argparse.Namespace) -> int:
    if not args.raw_dir.exists():
        raise FileNotFoundError(f"원천 데이터 디렉터리를 찾을 수 없습니다: {args.raw_dir}")

    config = load_retrieval_config(args.config) if args.config else load_retrieval_config()
    pipeline = RetrievalPipeline(config=config)

    result = pipeline.ingest(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        chunk_filename="chunks.jsonl",
        document_filename="documents.json",
        persist_outputs=True,
        skip_vectorstore=args.skip_vectorstore,
    )

    if not result.documents:
        logger.info("변경된 문서가 없어 종료합니다.")
        return 0

    if args.skip_vectorstore:
        logger.info("--skip-vectorstore 옵션으로 인해 벡터 저장을 생략합니다.")
        return 0

    logger.info("업서트된 청크 수: %d", result.upserted)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    return run_refresh_kb(args)


if __name__ == "__main__":
    raise SystemExit(main())
