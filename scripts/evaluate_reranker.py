"""리랭커 평가 및 디버깅 스크립트."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.config import load_retrieval_config
from src.retrieval.pipeline import RetrievalPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="평가할 후보 JSON/JSONL 파일 (score 필수)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="retrieval 설정 YAML 경로",
    )
    return parser.parse_args()


def load_candidates(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() in {".jsonl", ".jsonl.gz"}:
        return _load_jsonl(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            payload.append(json.loads(line))
    return payload


def summarize(scores: Iterable[float]) -> dict[str, float]:
    values = list(scores)
    return {
        "count": float(len(values)),
        "mean": mean(values) if values else 0.0,
        "min": min(values) if values else 0.0,
        "max": max(values) if values else 0.0,
    }


def main() -> None:
    args = parse_args()

    config = load_retrieval_config(args.config) if args.config else load_retrieval_config()
    pipeline = RetrievalPipeline(config=config)

    candidates = load_candidates(args.input)
    ranked = pipeline.rerank(candidates)

    scores = [item["score"] for item in ranked]
    normalized = [item.get("score_normalized", 0.0) for item in ranked]

    print("=== Ranked Top {} ===".format(len(ranked)))
    for idx, item in enumerate(ranked, start=1):
        title = item.get("metadata", {}).get("doc_title") or item.get("title") or "(no title)"
        print(f"[{idx:02d}] score={item['score']:.4f} norm={item.get('score_normalized', 0.0):.4f} title={title}")

    print("\n=== Score Summary ===")
    summary = summarize(scores)
    for key, value in summary.items():
        print(f"{key}: {value:.4f}")

    print("\n=== Normalized Score Summary ===")
    summary_norm = summarize(normalized)
    for key, value in summary_norm.items():
        print(f"{key}: {value:.4f}")


if __name__ == "__main__":
    main()
