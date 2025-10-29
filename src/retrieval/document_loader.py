"""문서 로딩/전처리 모듈."""

from __future__ import annotations


def load_documents(source_path: str) -> list[dict[str, str]]:
    """TODO: PDF/HTML/텍스트 파일을 로딩하고 클린징하세요."""
    raise NotImplementedError("문서 로딩 로직을 구현하세요.")


def chunk_documents(documents: list[dict[str, str]]) -> list[dict[str, str]]:
    """TODO: 청킹 규칙(길이/중복/메타데이터)을 정의하세요."""
    raise NotImplementedError("문서 청킹 로직을 구현하세요.")
