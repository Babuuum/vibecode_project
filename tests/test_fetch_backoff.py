import pytest

from autocontent.config import Settings
from autocontent.repos import ProjectRepository, SourceRepository, UserRepository
from autocontent.services.rss_fetcher import fetch_and_save_source


class FailingRSSClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def fetch(self, url: str) -> str:  # noqa: ARG002
        raise self.exc


@pytest.mark.asyncio
async def test_source_marked_broken_after_failures(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)

    user = await user_repo.create_user(tg_id=1234)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://broken")

    failing_client = FailingRSSClient(RuntimeError("boom"))
    threshold = Settings().source_fail_threshold
    for _ in range(threshold):
        await fetch_and_save_source(source.id, session, rss_client=failing_client)

    updated = await source_repo.get_by_id(source.id)
    assert updated is not None
    assert updated.status == "broken"
    assert updated.consecutive_failures == threshold
    assert "boom" in (updated.last_error or "")
