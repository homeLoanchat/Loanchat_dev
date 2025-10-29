"""Chroma 등 벡터스토어 관련 유틸."""

from __future__ import annotations


def init_vectorstore(collection_name: str):  # noqa: ANN001
    """TODO: 벡터스토어 클라이언트를 초기화하고 반환하세요."""
    raise NotImplementedError("벡터스토어 초기화를 구현하세요.")


def upsert_embeddings(collection, embeddings):  # noqa: ANN001, D401
    """TODO: 임베딩을 업서트하고 결과를 로깅하세요."""
    raise NotImplementedError("업서트 로직을 구현하세요.")
