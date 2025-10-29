"""데이터 적재/임베딩/그래프 테스트/평가 명령어를 제공하는 Typer CLI 진입점."""

from __future__ import annotations

import typer

app = typer.Typer(help="LoanBot 운영/배포 파이프라인 도구")


@app.command()
def build_index() -> None:
    """TODO: 최초 인덱스를 빌드하는 `scripts/build_index.py` 래퍼를 호출하세요."""
    raise NotImplementedError("build_index 커맨드를 구현하세요.")


@app.command()
def refresh_kb() -> None:
    """TODO: 증분 지식베이스 리프레시 절차를 구현하세요."""
    raise NotImplementedError("refresh_kb 커맨드를 구현하세요.")


@app.command()
def evaluate() -> None:
    """TODO: 오프라인 평가 루틴을 호출하고 요약 결과를 출력하세요."""
    raise NotImplementedError("evaluate 커맨드를 구현하세요.")


if __name__ == "__main__":
    app()
