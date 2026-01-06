from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.autocontent.config import Settings
from src.autocontent.domain import PostDraft, SourceItem
from src.autocontent.integrations.llm_client import LLMClient, LLMResponse
from src.autocontent.repos import (
    PostDraftRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
)
from src.autocontent.services.llm_gateway import LLMGateway
from src.autocontent.services.quota import NoopQuotaService, QuotaBackend
from src.autocontent.shared.text import compute_draft_hash as _compute_draft_hash, normalize_text


class DraftGenerationError(Exception):
    pass


class DraftService:
    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClient | None = None,
        settings: Settings | None = None,
        llm_gateway: LLMGateway | None = None,
        quota_service: QuotaBackend | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or Settings()
        self._items = SourceItemRepository(session)
        self._sources = SourceRepository(session)
        self._settings_repo = ProjectSettingsRepository(session)
        self._drafts = PostDraftRepository(session)
        if llm_gateway:
            self._llm_gateway = llm_gateway
        else:
            self._llm_gateway = LLMGateway(settings=self._settings, client=llm_client)
        self._quota = quota_service or NoopQuotaService()

    async def generate_draft(self, source_item_id: int, template_id: str | None = None) -> PostDraft:
        item = await self._items.get_by_id(source_item_id)
        if not item:
            raise DraftGenerationError("Source item not found")

        source = await self._sources.get_by_id(item.source_id)
        if not source:
            raise DraftGenerationError("Source not found")

        await self._quota.ensure_can_generate(source.project_id)

        settings = await self._settings_repo.get_by_project_id(source.project_id)
        max_post_len = settings.max_post_len if settings else self._settings.llm_max_tokens
        template_id = template_id or (settings.template_id if settings else None)
        language = settings.language if settings else "en"
        tone = settings.tone if settings else "friendly"
        niche = settings.niche if settings else "general"

        try:
            facts = item.facts_cache
            if not facts:
                facts = await self._extract_facts(item)
                await self._items.update_facts_cache(item.id, facts)
                item.facts_cache = facts

            content = await self._render_post(
                facts=facts, link=item.link, language=language, tone=tone, niche=niche, max_post_len=max_post_len
            )
        except Exception as exc:  # noqa: BLE001
            raise DraftGenerationError("LLM недоступен. Попробуйте позже.") from exc
        draft_hash = compute_draft_hash(
            project_id=source.project_id,
            source_item_id=item.id,
            template_id=template_id,
            raw_text=item.raw_text or "",
        )
        draft = await self._drafts.create_draft(
            project_id=source.project_id,
            source_item_id=item.id,
            template_id=template_id,
            text=content,
            draft_hash=draft_hash,
        )
        return draft

    async def list_drafts(self, project_id: int, limit: int = 10) -> list[PostDraft]:
        return await self._drafts.list_latest(project_id, limit=limit)

    async def get_draft(self, draft_id: int) -> PostDraft | None:
        return await self._drafts.get_by_id(draft_id)

    async def set_status(self, draft_id: int, status: str) -> None:
        await self._drafts.update_status(draft_id, status)

    async def reject_draft(self, draft_id: int) -> None:
        await self.set_status(draft_id, "rejected")

    async def _extract_facts(self, item: SourceItem) -> str:
        raw_text = normalize_text(item.raw_text or "")
        prompt = (
            "Extract 5 concise facts for a Telegram post from the following content.\n"
            "Keep facts short:\n"
            f"{raw_text}"
        )
        response = await self._llm_gateway.generate(prompt=prompt, max_post_len=512)
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
        response: LLMResponse = await self._llm_gateway.generate(
            prompt=prompt, max_post_len=max_post_len, seed=1
        )
        content = normalize_text(response.content)
        if link not in content:
            available_len = max_post_len - len(link) - 1
            if available_len < 0:
                available_len = 0
            if len(content) > available_len:
                content = content[:available_len]
            content = f"{content} {link}".strip()

        if len(content) > max_post_len:
            content = content[:max_post_len]
        return content


def compute_draft_hash(project_id: int, source_item_id: int, template_id: str | None, raw_text: str) -> str:
    return _compute_draft_hash(project_id, source_item_id, template_id, raw_text)
