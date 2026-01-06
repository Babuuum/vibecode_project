from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import Source
from autocontent.config import Settings
from autocontent.integrations.rss_client import HttpRSSClient, RSSClient
from autocontent.integrations.task_queue import TaskQueue
from autocontent.integrations.url_client import HttpURLClient, URLClient
from autocontent.repos import SourceItemRepository, SourceRepository
from autocontent.shared.lock import InMemoryLockStore, LockStore
from autocontent.shared.text import compute_content_hash, normalize_text


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
    task_queue: TaskQueue | None = None,
    lock_store: LockStore | None = None,
    max_items_per_run: int | None = None,
    url_client: URLClient | None = None,
) -> tuple[Source | None, int]:
    rss_client = rss_client or HttpRSSClient()
    url_client = url_client or HttpURLClient()

    source_repo = SourceRepository(session)
    source_item_repo = SourceItemRepository(session)

    source = await source_repo.get_by_id(source_id)
    if not source:
        return None, 0

    try:
        saved = 0
        created_items: list[int] = []
        if source.type == "url":
            settings = Settings()
            html = await url_client.fetch(source.url, settings.url_fetch_timeout_sec)
            if len(html) > settings.url_max_chars:
                html = html[: settings.url_max_chars]
            title, raw_text = extract_text_from_html(html, settings.url_text_max_chars)
            link = source.url
            external_id = link
            content_hash = compute_content_hash(link, title or "", raw_text)
            item = await source_item_repo.create_item(
                source_id=source.id,
                external_id=external_id,
                link=link,
                title=title or "(no title)",
                published_at=None,
                raw_text=raw_text,
                facts_cache=None,
                content_hash=content_hash,
            )
            if item:
                saved += 1
                created_items.append(item.id)
        else:
            raw_content = await rss_client.fetch(source.url)
            feed = feedparser.parse(raw_content)
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
                    created_items.append(item.id)

        await source_repo.update_status(
            source.id, status="ok", last_error=None, consecutive_failures=0
        )
        if created_items and task_queue:
            lock = lock_store or InMemoryLockStore()
            settings = Settings()
            ttl = settings.generate_lock_ttl
            if await lock.acquire(f"generate:{source.project_id}", ttl):
                limit = max_items_per_run or settings.max_generate_per_fetch
                for item_id in created_items[:limit]:
                    task_queue.enqueue_generate_draft(item_id)
        return source, saved
    except httpx.TimeoutException:
        await _handle_fetch_error(source, source_repo, "timeout")
        return source, 0
    except httpx.HTTPStatusError as exc:
        await _handle_fetch_error(source, source_repo, f"HTTP {exc.response.status_code}")
        return source, 0
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


async def _handle_fetch_error(source: Source, repo: SourceRepository, message: str) -> None:
    new_failures = (source.consecutive_failures or 0) + 1
    status = "error"
    if new_failures >= Settings().source_fail_threshold:
        status = "broken"
    await repo.update_status(
        source.id,
        status=status,
        last_error=message,
        consecutive_failures=new_failures,
    )


def extract_text_from_html(html: str, max_chars: int) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    text = soup.get_text(separator=" ", strip=True)
    normalized = normalize_text(text)
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars]
    return title, normalized
