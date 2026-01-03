from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import PostDraft


class PostDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, draft_hash: str) -> PostDraft | None:
        stmt = select(PostDraft).where(PostDraft.draft_hash == draft_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_draft(
        self,
        project_id: int,
        source_item_id: int,
        template_id: str | None,
        text: str,
        draft_hash: str,
        status: str = "new",
    ) -> PostDraft:
        existing = await self.get_by_hash(draft_hash)
        if existing:
            return existing

        draft = PostDraft(
            project_id=project_id,
            source_item_id=source_item_id,
            template_id=template_id,
            text=text,
            draft_hash=draft_hash,
            status=status,
        )
        self._session.add(draft)
        try:
            await self._session.commit()
            await self._session.refresh(draft)
            return draft
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_by_hash(draft_hash)
            if existing:
                return existing
            raise
