from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol


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


class MockLLMClient:
    def __init__(self, default_max_tokens: int = 128) -> None:
        self.default_max_tokens = default_max_tokens
        self._logger = logging.getLogger(__name__)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        max_tokens = request.max_tokens or self.default_max_tokens
        if request.max_post_len is not None:
            max_tokens = min(max_tokens, request.max_post_len)

        seed = request.seed if request.seed is not None else 0
        base = f"{seed}-{request.prompt}"
        content = base[:max_tokens]
        tokens_estimated = max(1, min(max_tokens, len(content) // 4 or 1))

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
