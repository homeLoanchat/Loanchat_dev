from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.config import RetrievalConfig, load_retrieval_config
from src.retrieval.pipeline import RetrievalPipeline


def test_pipeline_ingest_smoke(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "processed"
    raw_dir.mkdir()
    output_dir.mkdir()

    (raw_dir / "sample.txt").write_text("이것은 대출 한도에 대한 안내 문서입니다.", encoding="utf-8")

    base_config: RetrievalConfig = load_retrieval_config()
    vectorstore_path = tmp_path / "chroma"
    vectorstore = replace(base_config.vectorstore, persist_directory=vectorstore_path)
    config = replace(base_config, vectorstore=vectorstore)

    pipeline = RetrievalPipeline(config=config)
    result = pipeline.ingest(
        raw_dir=raw_dir,
        output_dir=output_dir,
        chunk_filename="chunks.jsonl",
        document_filename="documents.json",
        persist_outputs=True,
        skip_vectorstore=False,
    )

    assert result.documents, "최소 한 개의 문서는 처리되어야 합니다."
    assert result.upserted >= 1, "벡터스토어 업서트가 수행되어야 합니다."
    assert (output_dir / "chunks.jsonl").exists()
    assert (output_dir / "documents.json").exists()
