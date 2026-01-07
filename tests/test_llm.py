import json
import logging

import httpx
import pytest

from autocontent.config import Settings
from autocontent.integrations.llm_client import (
    LLMRequest,
    LLMResponse,
    MockLLMClient,
    RealLLMClient,
)
from autocontent.services.llm_gateway import LLMGateway


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


@pytest.mark.asyncio
async def test_mock_llm_deterministic_without_seed() -> None:
    client = MockLLMClient(default_max_tokens=6)
    req = LLMRequest(prompt="hello")

    resp1 = await client.generate(req)
    resp2 = await client.generate(req)

    assert resp1.content == resp2.content
    assert resp1.tokens_estimated == resp2.tokens_estimated


class _CapturingLLMClient:
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content="x" * 20, tokens_estimated=20)


@pytest.mark.asyncio
async def test_gateway_enforces_max_post_len_after_client() -> None:
    client = _CapturingLLMClient()
    settings = Settings(llm_mode="normal")
    gateway = LLMGateway(settings=settings, client=client)

    resp = await gateway.generate(prompt="hello", max_post_len=5)

    assert client.requests[0].max_tokens == min(settings.llm_max_tokens, 5)
    assert len(resp.content) == 5
    assert resp.tokens_estimated <= 5


@pytest.mark.asyncio
async def test_mock_llm_logs_event(caplog: pytest.LogCaptureFixture) -> None:
    client = MockLLMClient(default_max_tokens=4)
    caplog.set_level(logging.INFO)

    await client.generate(LLMRequest(prompt="abcd", seed=1))

    events = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        events.append(payload.get("event"))
    assert "llm_call" in events


@pytest.mark.asyncio
async def test_real_llm_retry_and_truncate() -> None:
    attempts: list[str] = []

    async def flaky_sender(payload: dict) -> str:
        attempts.append("try")
        if len(attempts) == 1:
            raise httpx.TimeoutException("timeout")
        return payload["prompt"] + "!"

    client = RealLLMClient(
        base_url="http://llm.local",
        api_key="key",
        default_max_tokens=5,
        max_retries=1,
        sender=flaky_sender,
    )

    request = LLMRequest(prompt="hello world")
    resp = await client.generate(request)

    assert len(attempts) == 2
    assert resp.content == "hello"
    assert resp.tokens_estimated >= 1
