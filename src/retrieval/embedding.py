"""임베딩 클라이언트 도우미."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, Sequence

import requests

from src.retrieval.config import EmbeddingConfig

logger = logging.getLogger(__name__)


class EmbeddingClient(Protocol):
    """텍스트를 벡터로 변환하는 인터페이스."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...


@dataclass(slots=True)
class HashEmbedder:
    """임시 폴백용 간단한 해시 임베더."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import hashlib

        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([byte / 255.0 for byte in digest])
        return vectors


@dataclass(slots=True)
class UpstageEmbedder:
    """Upstage Embedding API 클라이언트."""

    model_name: str
    api_key: str
    batch_size: int
    api_base: str | None = None
    timeout: float = 15.0
    _endpoint: str = field(init=False, repr=False)
    _session: requests.Session = field(init=False, repr=False)
    _fallback: HashEmbedder = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("Upstage Embedder를 사용하려면 api_key가 필요합니다.")
        endpoint = (self.api_base or "https://api.upstage.ai/v1/embeddings").rstrip("/")
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        object.__setattr__(self, "_endpoint", endpoint)
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_fallback", HashEmbedder())

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(texts), max(self.batch_size, 1)):
            batch = list(texts[start : start + max(self.batch_size, 1)])
            try:
                response = self._session.post(
                    self._endpoint,
                    json={"model": self.model_name, "input": batch},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:  # noqa: BLE001
                logger.error("Upstage 임베딩 호출 실패, 해시 임베더로 폴백합니다: %s", exc)
                return self._fallback.embed(texts)

            data = payload.get("data")
            if not isinstance(data, list) or len(data) != len(batch):
                logger.error("Upstage 응답 포맷이 올바르지 않습니다: %s", payload)
                return self._fallback.embed(texts)

            for item in data:
                vector = item.get("embedding")
                if not isinstance(vector, list) or not vector:
                    logger.error("Upstage 임베딩 벡터 포맷이 올바르지 않습니다: %s", item)
                    return self._fallback.embed(texts)
                embeddings.append([float(value) for value in vector])

        return embeddings


def create_embedder(config: EmbeddingConfig) -> EmbeddingClient:
    """설정에 따라 임베딩 클라이언트를 생성한다."""

    provider = config.provider.lower()
    if provider == "upstage":
        if not config.api_key:
            logger.warning("Upstage API key가 없어 해시 임베더로 폴백합니다.")
            return HashEmbedder()
        return UpstageEmbedder(
            model_name=config.model_name,
            api_key=config.api_key or "",
            batch_size=config.batch_size,
            api_base=config.api_base,
            timeout=config.timeout,
        )
    if provider == "openai":
        raise NotImplementedError("OpenAI 임베딩 제공자는 아직 구현되지 않았습니다.")
    
    raise ValueError(f"지원하지 않는 임베딩 provider입니다: {config.provider}")


__all__ = [
    "EmbeddingClient",
    "HashEmbedder",
    "UpstageEmbedder",
    "create_embedder",
]
