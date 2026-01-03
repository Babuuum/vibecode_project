from __future__ import annotations

from autocontent.config import Settings
from autocontent.integrations.llm_client import LLMClient, LLMRequest, LLMResponse, MockLLMClient


class LLMGateway:
    def __init__(self, settings: Settings | None = None, client: LLMClient | None = None) -> None:
        self.settings = settings or Settings()
        self.client = client or self._build_client()

    def _build_client(self) -> LLMClient:
        # Placeholder: only mock client for now
        return MockLLMClient(default_max_tokens=self.settings.llm_max_tokens)

    async def generate(
        self, prompt: str, max_tokens: int | None = None, max_post_len: int | None = None, seed: int | None = None
    ) -> LLMResponse:
        request = LLMRequest(
            prompt=prompt,
            max_tokens=max_tokens or self.settings.llm_max_tokens,
            max_post_len=max_post_len,
            seed=seed,
        )
        return await self.client.generate(request)
