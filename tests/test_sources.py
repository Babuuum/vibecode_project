import pytest
from sqlalchemy import select

from src.autocontent.domain import SourceItem
from src.autocontent.repos import ProjectRepository, SourceRepository, UserRepository
from src.autocontent.services.rss_fetcher import fetch_and_save_source

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <link>http://example.com/</link>
  <description>Test feed</description>
  <item>
    <title>First</title>
    <link>http://example.com/1</link>
    <guid>1</guid>
    <pubDate>Mon, 06 Sep 2021 00:01:00 +0000</pubDate>
    <description>Hello world</description>
  </item>
  <item>
    <title>Second</title>
    <link>http://example.com/2</link>
    <guid>2</guid>
    <pubDate>Mon, 06 Sep 2021 00:02:00 +0000</pubDate>
    <description>Hello again</description>
  </item>
</channel>
</rss>
"""


class FakeRSSClient:
    async def fetch(self, url: str) -> str:  # noqa: ARG002
        return RSS_SAMPLE


@pytest.mark.asyncio
async def test_deduplication(session):
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)

    user = await user_repo.create_user(tg_id=123)
    project = await project_repo.create_project(owner_user_id=user.id, title="Proj", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")

    rss_client = FakeRSSClient()
    _, saved_first = await fetch_and_save_source(source.id, session, rss_client=rss_client)
    _, saved_second = await fetch_and_save_source(source.id, session, rss_client=rss_client)

    assert saved_first == 2
    assert saved_second == 0


@pytest.mark.asyncio
async def test_fetch_and_save_integration(session):
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    user = await user_repo.create_user(tg_id=124)
    project = await project_repo.create_project(owner_user_id=user.id, title="Proj2", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")

    rss_client = FakeRSSClient()
    source_after, saved = await fetch_and_save_source(source.id, session, rss_client=rss_client)

    assert source_after is not None
    assert source_after.status == "ok"
    assert saved == 2
    items = await session.execute(select(SourceItem).where(SourceItem.source_id == source.id))
    assert all(item.content_hash for item in items.scalars().all())
