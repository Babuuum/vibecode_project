import pytest

from autocontent.config import Settings
from autocontent.services.llm_gateway import LLMGateway
from autocontent.integrations.llm_client import LLMRequest, MockLLMClient


@pytest.mark.asyncio
async def test_mock_llm_deterministic_seed() -> None:
    client = MockLLMClient(default_max_tokens=10)
    req1 = LLMRequest(prompt="hello world", seed=1)
    req2 = LLMRequest(prompt="hello world", seed=1)

    resp1 = await client.generate(req1)
    resp2 = await client.generate(req2)

    assert resp1.content == resp2.content
    assert resp1.tokens_estimated == resp2.tokens_estimated


@pytest.mark.asyncio
async def test_economy_mode_enforces_max_tokens() -> None:
    settings = Settings(llm_mode="economy")
    gateway = LLMGateway(settings=settings)

    resp = await gateway.generate(prompt="x" * 500, max_post_len=50)

    assert len(resp.content) <= settings.llm_max_tokens
    assert len(resp.content) <= 50
