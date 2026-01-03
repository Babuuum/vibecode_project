from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

import httpx


@dataclass
class LLMRequest:
    prompt: str
    max_tokens: int | None = None
    seed: int | None = None
    max_post_len: int | None = None


@dataclass
class LLMResponse:
    content: str
    tokens_estimated: int


class LLMClient(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError


def _estimate_tokens(content: str, max_tokens: int) -> int:
    return max(1, min(max_tokens, max(1, len(content) // 4)))


def _apply_max(request: LLMRequest, default_max_tokens: int) -> int:
    max_tokens = request.max_tokens or default_max_tokens
    if request.max_post_len is not None:
        max_tokens = min(max_tokens, request.max_post_len)
    return max_tokens


class MockLLMClient:
    def __init__(self, default_max_tokens: int = 128) -> None:
        self.default_max_tokens = default_max_tokens
        self._logger = logging.getLogger(__name__)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        max_tokens = _apply_max(request, self.default_max_tokens)

        seed = request.seed if request.seed is not None else 0
        base = f"{seed}-{request.prompt}"
        content = base[:max_tokens]
        tokens_estimated = _estimate_tokens(content, max_tokens)

        duration_ms = int((time.perf_counter() - start) * 1000)
        self._logger.info(
            "LLM call",
            extra={
                "event": "llm_call",
                "duration_ms": duration_ms,
                "tokens_estimated": tokens_estimated,
            },
        )
        return LLMResponse(content=content, tokens_estimated=tokens_estimated)


class RealLLMClient:
    """Stub real client with retry/timeout; response echoes prompt slice."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        default_max_tokens: int = 256,
        max_retries: int = 2,
        timeout: float = 10.0,
        sender: Callable[[dict], Awaitable[str]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_max_tokens = default_max_tokens
        self.max_retries = max_retries
        self.timeout = timeout
        self._logger = logging.getLogger(__name__)
        self._sender = sender or self._send_http

    async def _send_http(self, payload: dict) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/generate", json=payload, headers={"Authorization": f"Bearer {self.api_key}"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("content", "")

    async def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        max_tokens = _apply_max(request, self.default_max_tokens)
        payload = {"prompt": request.prompt, "max_tokens": max_tokens}
        attempt = 0
        last_exc: Exception | None = None

        while attempt <= self.max_retries:
            try:
                raw_content = await self._sender(payload)
                content = (raw_content or "")[:max_tokens]
                tokens_estimated = _estimate_tokens(content, max_tokens)
                duration_ms = int((time.perf_counter() - start) * 1000)
                self._logger.info(
                    "LLM call",
                    extra={
                        "event": "llm_call",
                        "duration_ms": duration_ms,
                        "tokens_estimated": tokens_estimated,
                        "attempt": attempt + 1,
                    },
                )
                return LLMResponse(content=content, tokens_estimated=tokens_estimated)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                attempt += 1
                if attempt > self.max_retries:
                    raise
                await self._backoff(attempt)
        raise last_exc or RuntimeError("LLM call failed")

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(min(0.1 * attempt, 1))
