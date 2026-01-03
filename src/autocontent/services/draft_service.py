from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.config import Settings
from autocontent.domain import PostDraft
from autocontent.integrations.llm_client import LLMClient
from autocontent.repos import (
    PostDraftRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
)
from autocontent.services.llm_gateway import LLMGateway


def compute_draft_hash(
    project_id: int, source_item_id: int, template_id: str | None, raw_text: str
) -> str:
    payload = "|".join([str(project_id), str(source_item_id), template_id or "", raw_text.strip()])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DraftService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        llm_client: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or Settings()
        self._llm_gateway = LLMGateway(settings=self._settings, client=llm_client)
        self._source_items = SourceItemRepository(session)
        self._sources = SourceRepository(session)
        self._settings_repo = ProjectSettingsRepository(session)
        self._drafts = PostDraftRepository(session)

    async def generate_draft(self, source_item_id: int, template_id: str | None = None) -> PostDraft:
        item = await self._source_items.get_by_id(source_item_id)
        if not item:
            raise ValueError("Source item not found")

        source = await self._sources.get_by_id(item.source_id)
        if not source:
            raise ValueError("Source not found")

        project_settings = await self._settings_repo.get_by_project_id(source.project_id)
        max_len = project_settings.max_post_len if project_settings else self._settings.llm_max_tokens

        text_input = (item.raw_text or item.title or "").strip()
        facts_prompt = (
            "Extract key facts for a short post. Return a compact bullet-like string without markup.\n"
            f"Source:\n{text_input}"
        )
        facts_resp = await self._llm_gateway.generate(
            prompt=facts_prompt,
            max_post_len=max_len,
            max_tokens=max_len,
            seed=item.id,
        )
        facts = facts_resp.content.strip()

        post_prompt = (
            f"Write a short social post under {max_len} characters using these facts. "
            "No hashtags, keep concise:\n"
            f"{facts}"
        )
        post_resp = await self._llm_gateway.generate(
            prompt=post_prompt,
            max_post_len=max_len,
            max_tokens=max_len,
            seed=item.id + 1,
        )
        text = post_resp.content.strip()
        text = self._append_link(text, item.link, max_len)

        draft_hash = compute_draft_hash(
            project_id=source.project_id,
            source_item_id=item.id,
            template_id=template_id,
            raw_text=text_input,
        )

        return await self._drafts.create_draft(
            project_id=source.project_id,
            source_item_id=item.id,
            template_id=template_id,
            text=text,
            draft_hash=draft_hash,
            status="new",
        )

    def _append_link(self, text: str, link: str | None, max_len: int) -> str:
        if not link:
            return text[:max_len]

        body_limit = max_len - len(link) - 1
        body_limit = max(body_limit, 0)
        trimmed_text = text[:body_limit] if body_limit else ""
        if link in text:
            trimmed_text = text
        combined = (trimmed_text.rstrip() + "\n" + link).strip()
        return combined[:max_len]
