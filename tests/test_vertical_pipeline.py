import pytest

from autocontent.integrations.task_queue import TaskQueue
from autocontent.repos import ProjectRepository, SourceRepository, UserRepository
from autocontent.services.rss_fetcher import fetch_and_save_source
from autocontent.shared.lock import InMemoryLockStore


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

RSS_SAMPLE_2 = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <link>http://example.com/</link>
  <description>Test feed</description>
  <item>
    <title>Third</title>
    <link>http://example.com/3</link>
    <guid>3</guid>
    <pubDate>Mon, 06 Sep 2021 00:03:00 +0000</pubDate>
    <description>New entry</description>
  </item>
</channel>
</rss>
"""

class FakeRSSClient:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    async def fetch(self, url: str) -> str:  # noqa: ARG002
        return self._payload


class FakeQueue(TaskQueue):
    def __init__(self) -> None:
        self.items: list[int] = []

    def enqueue_generate_draft(self, source_item_id: int) -> None:
        self.items.append(source_item_id)

    def enqueue_publish_draft(self, draft_id: int) -> None:  # noqa: ARG002
        return None


@pytest.mark.asyncio
async def test_fetch_enqueues_generate(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)

    user = await user_repo.create_user(tg_id=800)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")

    queue = FakeQueue()
    lock_store = InMemoryLockStore()

    _, saved = await fetch_and_save_source(
        source.id,
        session,
        rss_client=FakeRSSClient(RSS_SAMPLE),
        task_queue=queue,
        lock_store=lock_store,
        max_items_per_run=1,
    )

    assert saved == 2
    assert len(queue.items) == 1


@pytest.mark.asyncio
async def test_fetch_lock_prevents_duplicate_enqueue(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)

    user = await user_repo.create_user(tg_id=801)
    project = await project_repo.create_project(owner_user_id=user.id, title="P2", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed2")

    queue = FakeQueue()
    lock_store = InMemoryLockStore()

    await fetch_and_save_source(
        source.id,
        session,
        rss_client=FakeRSSClient(RSS_SAMPLE),
        task_queue=queue,
        lock_store=lock_store,
        max_items_per_run=2,
    )
    await fetch_and_save_source(
        source.id,
        session,
        rss_client=FakeRSSClient(RSS_SAMPLE_2),
        task_queue=queue,
        lock_store=lock_store,
        max_items_per_run=2,
    )

    assert len(queue.items) == 2
