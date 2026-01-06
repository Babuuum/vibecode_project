from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import feedparser
from sqlalchemy.ext.asyncio import AsyncSession

from src.autocontent.domain import Source
from src.autocontent.config import Settings
from src.autocontent.integrations.rss_client import HttpRSSClient, RSSClient
from src.autocontent.repos import SourceItemRepository, SourceRepository
from src.autocontent.shared.text import compute_content_hash, normalize_text


def _parse_datetime(entry: dict) -> datetime | None:
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if not published:
        return None
    return datetime(*published[:6], tzinfo=timezone.utc)


def _extract_entries(feed) -> Iterable[dict]:
    return feed.entries if hasattr(feed, "entries") else []


async def fetch_and_save_source(
    source_id: int,
    session: AsyncSession,
    rss_client: RSSClient | None = None,
) -> tuple[Source | None, int]:
    rss_client = rss_client or HttpRSSClient()

    source_repo = SourceRepository(session)
    source_item_repo = SourceItemRepository(session)

    source = await source_repo.get_by_id(source_id)
    if not source:
        return None, 0

    try:
        raw_content = await rss_client.fetch(source.url)
        feed = feedparser.parse(raw_content)
        saved = 0
        for entry in _extract_entries(feed):
            link = entry.get("link") or ""
            title = entry.get("title") or "(no title)"
            external_id = entry.get("id") or link or title
            published_at = _parse_datetime(entry)
            raw_text = normalize_text(entry.get("summary") or entry.get("description") or "")
            content_hash = compute_content_hash(link, title, raw_text)

            item = await source_item_repo.create_item(
                source_id=source.id,
                external_id=external_id,
                link=link,
                title=title,
                published_at=published_at,
                raw_text=raw_text,
                facts_cache=None,
                content_hash=content_hash,
            )
            if item:
                saved += 1

        await source_repo.update_status(
            source.id, status="ok", last_error=None, consecutive_failures=0
        )
        return source, saved
    except Exception as exc:  # noqa: BLE001
        new_failures = (source.consecutive_failures or 0) + 1
        status = "error"
        if new_failures >= Settings().source_fail_threshold:
            status = "broken"
        await source_repo.update_status(
            source_id,
            status=status,
            last_error=str(exc),
            consecutive_failures=new_failures,
        )
        return source, 0
