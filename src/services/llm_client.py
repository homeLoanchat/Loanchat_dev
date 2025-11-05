"""Simple Upstage chat client used by retrieval composers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Mapping, MutableMapping

import requests

logger = logging.getLogger(__name__)


class ChatCompletionError(RuntimeError):
    """Raised when the LLM call returns an unexpected payload."""


def _normalise_messages(messages: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Return messages as a list of plain dicts (requests friendly)."""

    result: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if not role or not content:
            raise ChatCompletionError("Each message must include non-empty role and content.")
        result.append({"role": role, "content": content})
    return result


@dataclass
class UpstageChatClient:
    """Minimal Upstage chat completions client."""

    api_key: str
    model: str = "solar-pro2"
    api_base: str = "https://api.upstage.ai/v1"
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("Upstage API key is required.")
        base = self.api_base.rstrip("/")
        self._endpoint = f"{base}/chat/completions"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "LoanBot/1.0",
            }
        )

    def complete(
        self,
        messages: Iterable[Mapping[str, str]],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 768,
        extra: MutableMapping[str, object] | None = None,
    ) -> str:
        """Call the Upstage chat completions API and return the response text."""

        payload: dict[str, object] = {
            "model": self.model,
            "messages": _normalise_messages(messages),
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if extra:
            payload.update(extra)

        try:
            response = self._session.post(self._endpoint, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:  # pragma: no cover - network failure
            logger.error("Upstage chat request failed: %s", exc)
            raise

        if response.status_code >= 400:
            # Upstage는 400에서 응답 본문에 상세 사유를 내려주므로 그대로 로그 남김
            logger.error(
                "Upstage chat request failed status=%s body=%s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ChatCompletionError(f"Unexpected response payload: {data!r}")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ChatCompletionError(f"Missing chat message in response: {choices[0]!r}")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ChatCompletionError(f"Empty chat completion content: {message!r}")

        return content.strip()

    def close(self) -> None:
        """Release the underlying HTTP session."""

        self._session.close()


__all__ = ["ChatCompletionError", "UpstageChatClient"]
