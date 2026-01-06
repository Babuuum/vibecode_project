from __future__ import annotations

from typing import Protocol

import httpx


class URLClient(Protocol):
    async def fetch(self, url: str, timeout_sec: int) -> str:
        raise NotImplementedError


class HttpURLClient:
    async def fetch(self, url: str, timeout_sec: int) -> str:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
