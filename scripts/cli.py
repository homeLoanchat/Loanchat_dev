"""데이터 적재/임베딩/그래프 테스트/평가 명령어를 제공하는 Typer CLI 진입점."""

from __future__ import annotations

from pathlib import Path
from typing import List

import typer

from scripts.build_index import main as build_index_main
from scripts.evaluate_reranker import main as evaluate_reranker_main
from scripts.refresh_kb import main as refresh_kb_main

app = typer.Typer(help="LoanBot 운영/배포 파이프라인 도구")


def _maybe_add(args: List[str], flag: str, value: Path | str | None) -> None:
    if value is None:
        return
    args.extend([flag, str(value)])


@app.command("build-index")
def build_index(
    config: Path | None = typer.Option(None, help="retrieval 설정 YAML 경로"),
    raw_dir: Path = typer.Option(Path("data/raw"), help="원천 데이터 디렉터리"),
    output_dir: Path = typer.Option(Path("data/processed"), help="청킹 결과 저장 디렉터리"),
    skip_vectorstore: bool = typer.Option(False, help="벡터스토어 업서트를 생략"),
    log_level: str = typer.Option("INFO", help="로깅 레벨", case_sensitive=False),
) -> None:
    argv: List[str] = []
    _maybe_add(argv, "--raw-dir", raw_dir)
    _maybe_add(argv, "--output-dir", output_dir)
    _maybe_add(argv, "--config", config)
    if skip_vectorstore:
        argv.append("--skip-vectorstore")
    _maybe_add(argv, "--log-level", log_level)

    exit_code = build_index_main(argv)
    raise typer.Exit(exit_code)


@app.command("refresh-kb")
def refresh_kb(
    config: Path | None = typer.Option(None, help="retrieval 설정 YAML 경로"),
    raw_dir: Path = typer.Option(Path("data/raw"), help="증분 업데이트할 데이터 디렉터리"),
    output_dir: Path = typer.Option(Path("data/processed"), help="청킹 결과 저장 디렉터리"),
    skip_vectorstore: bool = typer.Option(False, help="벡터스토어 업서트를 생략"),
    log_level: str = typer.Option("INFO", help="로깅 레벨", case_sensitive=False),
) -> None:
    argv: List[str] = []
    _maybe_add(argv, "--raw-dir", raw_dir)
    _maybe_add(argv, "--output-dir", output_dir)
    _maybe_add(argv, "--config", config)
    if skip_vectorstore:
        argv.append("--skip-vectorstore")
    _maybe_add(argv, "--log-level", log_level)

    exit_code = refresh_kb_main(argv)
    raise typer.Exit(exit_code)


@app.command("evaluate-reranker")
def evaluate_reranker(
    input_path: Path = typer.Option(..., "--input", help="평가할 후보 JSON/JSONL 경로"),
    config: Path | None = typer.Option(None, help="retrieval 설정 YAML 경로"),
) -> None:
    argv: List[str] = ["--input", str(input_path)]
    _maybe_add(argv, "--config", config)
    exit_code = evaluate_reranker_main(argv)
    raise typer.Exit(exit_code)


if __name__ == "__main__":  # pragma: no cover
    app()
