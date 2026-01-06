from __future__ import annotations

from autocontent.config import Settings
from autocontent.integrations.llm_client import (
    LLMClient,
    LLMRequest,
    LLMResponse,
    MockLLMClient,
    RealLLMClient,
)


class LLMGateway:
    def __init__(self, settings: Settings | None = None, client: LLMClient | None = None) -> None:
        self.settings = settings or Settings()
        self.client = client or self._build_client()

    def _build_client(self) -> LLMClient:
        provider = (self.settings.llm_provider or "mock").lower()
        if provider == "mock":
            return MockLLMClient(default_max_tokens=self.settings.llm_max_tokens)
        if provider == "real":
            return RealLLMClient(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
                default_max_tokens=self.settings.llm_max_tokens,
            )
        raise ValueError(f"Unsupported llm_provider: {self.settings.llm_provider}")

    async def generate(
        self, prompt: str, max_tokens: int | None = None, max_post_len: int | None = None, seed: int | None = None
    ) -> LLMResponse:
        resolved_max_tokens = max_tokens or self.settings.llm_max_tokens
        if max_post_len is not None:
            resolved_max_tokens = min(resolved_max_tokens, max_post_len)

        request = LLMRequest(
            prompt=prompt,
            max_tokens=resolved_max_tokens,
            max_post_len=max_post_len,
            seed=seed,
        )
        response = await self.client.generate(request)

        if max_post_len is not None and len(response.content) > max_post_len:
            response = LLMResponse(
                content=response.content[:max_post_len],
                tokens_estimated=min(response.tokens_estimated, max_post_len),
            )
        return response
