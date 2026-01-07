import pytest
from httpx import AsyncClient

from autocontent.api.main import create_app
from autocontent.config import Settings


@pytest.mark.asyncio
async def test_request_id_added_when_missing() -> None:
    app = create_app(
        Settings(postgres_dsn="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true")
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_request_id_echoed() -> None:
    app = create_app(
        Settings(postgres_dsn="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true")
    )
    request_id = "req-123"

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/healthz", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id
