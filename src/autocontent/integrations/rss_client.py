from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class RSSClient(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> str:
        raise NotImplementedError


class HttpRSSClient(RSSClient):
    async def fetch(self, url: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            response.raise_for_status()
            return response.text
