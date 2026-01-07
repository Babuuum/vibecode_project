from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import PostDraft, SourceItem
from autocontent.shared.text import compute_draft_hash as compute_draft_hash_value


class PostDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, draft_hash: str) -> PostDraft | None:
        stmt = select(PostDraft).where(PostDraft.draft_hash == draft_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, draft_id: int) -> PostDraft | None:
        stmt = select(PostDraft).where(PostDraft.id == draft_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_recent_hash(self, draft_hash: str, since: datetime) -> bool:
        stmt = select(PostDraft).where(
            PostDraft.draft_hash == draft_hash,
            PostDraft.created_at >= since,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_recent_content_hash(self, content_hash: str, since: datetime) -> bool:
        stmt = (
            select(PostDraft)
            .join(SourceItem, SourceItem.id == PostDraft.source_item_id)
            .where(
                SourceItem.content_hash == content_hash,
                PostDraft.created_at >= since,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update_status(self, draft_id: int, status: str) -> None:
        draft = await self.get_by_id(draft_id)
        if not draft:
            return
        draft.status = status
        self._session.add(draft)
        await self._session.commit()
        await self._session.refresh(draft)

    async def list_latest(self, project_id: int, limit: int = 10) -> list[PostDraft]:
        stmt = (
            select(PostDraft)
            .where(PostDraft.project_id == project_id)
            .order_by(PostDraft.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_project(
        self, project_id: int, status: str | None = None, limit: int = 50
    ) -> list[PostDraft]:
        stmt = select(PostDraft).where(PostDraft.project_id == project_id)
        if status:
            stmt = stmt.where(PostDraft.status == status)
        stmt = stmt.order_by(PostDraft.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_ready(self, project_id: int) -> PostDraft | None:
        stmt = (
            select(PostDraft)
            .where(PostDraft.project_id == project_id, PostDraft.status == "ready")
            .order_by(PostDraft.created_at.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count(self) -> int:
        stmt = select(PostDraft)
        result = await self._session.execute(stmt)
        return len(list(result.scalars()))

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

    @staticmethod
    def compute_draft_hash(
        project_id: int, source_item_id: int, template_id: str | None, raw_text: str
    ) -> str:
        return compute_draft_hash_value(project_id, source_item_id, template_id, raw_text)
