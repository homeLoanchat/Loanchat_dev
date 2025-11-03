"""데이터 적재/임베딩/그래프 테스트/평가 명령어를 제공하는 Typer CLI 진입점."""

from __future__ import annotations

import typer

from scripts.build_index import main as build_index_main
from scripts.evaluate import main as evaluate_main
from scripts.refresh_kb import main as refresh_kb_main

app = typer.Typer(help="LoanBot 운영/배포 파이프라인 도구")


@app.command()
def build_index() -> None:
    """Retrieval 인덱스를 생성한다."""

    exit_code = build_index_main([])
    raise typer.Exit(exit_code)


@app.command()
def refresh_kb() -> None:
    """지식베이스를 증분 갱신한다."""

    try:
        refresh_kb_main()
    except NotImplementedError as exc:  # pragma: no cover - 추후 구현 예정
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1) from exc


@app.command()
def evaluate() -> None:
    """오프라인 평가 루틴을 실행한다."""

    try:
        evaluate_main()
    except NotImplementedError as exc:  # pragma: no cover - 추후 구현 예정
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    app()
