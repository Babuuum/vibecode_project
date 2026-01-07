import pytest

from autocontent.repos import (
    ProjectRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.rss_fetcher import extract_text_from_html, fetch_and_save_source

HTML_SAMPLE = """
<html>
  <head><title>Sample Page</title></head>
  <body>
    <h1>Header</h1>
    <p>First paragraph.</p>
    <p>Second paragraph.</p>
    <script>var x = 1;</script>
  </body>
</html>
"""


class FakeURLClient:
    def __init__(self, html: str) -> None:
        self._html = html

    async def fetch(self, url: str, timeout_sec: int) -> str:  # noqa: ARG002
        return self._html


@pytest.mark.asyncio
async def test_html_extractor_basic() -> None:
    title, text = extract_text_from_html(HTML_SAMPLE, max_chars=1000)
    assert title == "Sample Page"
    assert "Header" in text
    assert "First paragraph." in text
    assert "script" not in text.lower()


@pytest.mark.asyncio
async def test_url_source_fetch_and_dedup(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=950)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    source = await source_repo.create_source(
        project_id=project.id, url="http://example.com/page", type="url"
    )

    url_client = FakeURLClient(HTML_SAMPLE)
    _, saved_first = await fetch_and_save_source(
        source.id,
        session,
        url_client=url_client,
    )
    _, saved_second = await fetch_and_save_source(
        source.id,
        session,
        url_client=url_client,
    )

    assert saved_first == 1
    assert saved_second == 0
    item = await item_repo.get_latest_new_for_project(project.id)
    assert item is not None
    assert "First paragraph." in (item.raw_text or "")
