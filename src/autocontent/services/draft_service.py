from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.config import Settings
from autocontent.domain import PostDraft, SourceItem
from autocontent.integrations.llm_client import LLMResponse
from autocontent.repos import (
    PostDraftRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
)
from autocontent.services.llm_gateway import LLMGateway
from autocontent.shared.text import normalize_text


class DraftGenerationError(Exception):
    pass


@dataclass
class DraftContext:
    source_item: SourceItem
    facts: str
    content: str
    draft: PostDraft


class DraftService:
    def __init__(
        self, session: AsyncSession, llm_gateway: LLMGateway | None = None, settings: Settings | None = None
    ) -> None:
        self._session = session
        self._settings = settings or Settings()
        self._items = SourceItemRepository(session)
        self._sources = SourceRepository(session)
        self._settings_repo = ProjectSettingsRepository(session)
        self._drafts = PostDraftRepository(session)
        self._llm = llm_gateway or LLMGateway(settings=self._settings)

    async def generate_draft(self, source_item_id: int, template_id: str | None = None) -> DraftContext:
        item = await self._items.get_by_id(source_item_id)
        if not item:
            raise DraftGenerationError("Source item not found")

        source = await self._sources.get_by_id(item.source_id)
        if not source:
            raise DraftGenerationError("Source not found")

        settings = await self._settings_repo.get_by_project_id(source.project_id)
        max_post_len = settings.max_post_len if settings else self._settings.llm_max_tokens
        template_id = template_id or (settings.template_id if settings else None)
        language = settings.language if settings else "en"
        tone = settings.tone if settings else "friendly"
        niche = settings.niche if settings else "general"

        facts = item.facts_cache
        if not facts:
            facts = await self._extract_facts(item)
            await self._items.update_facts_cache(item.id, facts)
            item.facts_cache = facts

        content = await self._render_post(
            facts=facts, link=item.link, language=language, tone=tone, niche=niche, max_post_len=max_post_len
        )
        draft_hash = self._drafts.compute_draft_hash(source_item_id=item.id, text=content)
        draft = await self._drafts.create_draft(
            project_id=source.project_id,
            source_item_id=item.id,
            template_id=template_id,
            text=content,
            draft_hash=draft_hash,
            status="draft",
        )
        return DraftContext(source_item=item, facts=facts, content=content, draft=draft)

    async def list_drafts(self, project_id: int, limit: int = 10) -> list[PostDraft]:
        return await self._drafts.list_latest(project_id, limit=limit)

    async def get_draft(self, draft_id: int) -> PostDraft | None:
        return await self._drafts.get_by_id(draft_id)

    async def _extract_facts(self, item: SourceItem) -> str:
        raw_text = normalize_text(item.raw_text or "")
        prompt = (
            "Extract 5 concise facts for a Telegram post from the following content.\n"
            "Keep facts short:\n"
            f"{raw_text}"
        )
        response = await self._llm.generate(prompt=prompt, max_post_len=512)
        return normalize_text(response.content)

    async def _render_post(
        self, facts: str, link: str, language: str, tone: str, niche: str, max_post_len: int
    ) -> str:
        prompt = (
            f"Language: {language}. Tone: {tone}. Niche: {niche}.\n"
            "Create a short Telegram post using the facts and include the source link at the end.\n"
            f"Facts:\n{facts}\n"
            f"Link: {link}\n"
            "Return plain text only."
        )
        response: LLMResponse = await self._llm.generate(
            prompt=prompt, max_post_len=max_post_len, seed=1
        )
        content = response.content
        if link not in content:
            content = f"{content}\n{link}"

        normalized = normalize_text(content)
        if len(normalized) > max_post_len:
            normalized = normalized[:max_post_len]
        return normalized
