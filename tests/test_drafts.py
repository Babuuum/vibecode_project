from datetime import UTC, datetime

import pytest

from autocontent.config import Settings
from autocontent.integrations.llm_client import LLMClient, LLMResponse, MockLLMClient
from autocontent.repos import (
    ProjectRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.draft_service import DraftService, compute_draft_hash
from autocontent.services.quota import QuotaExceededError, QuotaService


class FakeLLM(LLMClient):
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses

    async def generate(self, request) -> LLMResponse:  # type: ignore[override]
        content = self._responses.pop(0)
        return LLMResponse(content=content, tokens_estimated=max(1, len(content) // 4))


class FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.storage[key] = self.storage.get(key, 0) + 1
        return self.storage[key]

    async def expire(self, key: str, ttl: int) -> None:  # noqa: ARG002
        return None


@pytest.mark.asyncio
async def test_generate_draft_limits_length_and_hash(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=321)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await settings_repo.create_settings(
        project_id=project.id, language="ru", niche="tech", tone="friendly", max_post_len=50
    )
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="1",
        link="http://example.com/1",
        title="Title",
        published_at=datetime.now(UTC),
        raw_text="A" * 200,
        content_hash="hash1",
    )

    llm = FakeLLM(responses=["fact " * 20, "post " * 20])
    service = DraftService(session, llm_client=llm, settings=Settings(llm_mode="economy"))

    draft = await service.generate_draft(item.id)

    assert len(draft.text) <= 50
    assert draft.draft_hash == compute_draft_hash(
        project_id=project.id, source_item_id=item.id, template_id=None, raw_text="A" * 200
    )


@pytest.mark.asyncio
async def test_generate_draft_with_mock_llm(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=654)
    project = await project_repo.create_project(owner_user_id=user.id, title="P2", tz="UTC")
    await settings_repo.create_settings(
        project_id=project.id, language="en", niche="tech", tone="formal", max_post_len=120
    )
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="2",
        link="http://example.com/2",
        title="Another title",
        published_at=datetime.now(UTC),
        raw_text="Hello world from RSS item",
        content_hash="hash2",
    )

    llm = MockLLMClient(default_max_tokens=60)
    service = DraftService(session, llm_client=llm, settings=Settings(llm_mode="normal"))

    draft = await service.generate_draft(item.id)

    assert draft.project_id == project.id
    assert draft.source_item_id == item.id
    assert "http://example.com/2" in draft.text
    assert draft.status == "new"


@pytest.mark.asyncio
async def test_generate_draft_blocked_by_quota(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=777)
    project = await project_repo.create_project(owner_user_id=user.id, title="QP", tz="UTC")
    await settings_repo.create_settings(
        project_id=project.id, language="en", niche="tech", tone="formal"
    )
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/quota")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="q1",
        link="http://example.com/q1",
        title="quota",
        published_at=None,
        raw_text="text",
        facts_cache=None,
        content_hash="hashq1",
    )
    assert item is not None

    redis = FakeRedis()
    settings = Settings(drafts_per_day=1)
    quota = QuotaService(redis, settings=settings)
    service = DraftService(
        session,
        llm_client=MockLLMClient(default_max_tokens=10),
        settings=settings,
        quota_service=quota,
    )

    await service.generate_draft(item.id)
    with pytest.raises(QuotaExceededError):
        await service.generate_draft(item.id)
