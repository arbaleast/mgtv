"""芒果 TV API 客户端。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp

from .fetcher import fetch_all, ChannelResult

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)


class MgtvClient:
    """芒果 TV API 客户端。"""

    def __init__(self, settings: Settings | None = None):
        from ..config import settings as _settings
        self.settings = settings or _settings

    async def fetch_all(self, channels: list[dict]) -> list[ChannelResult]:
        """并发请求所有频道。"""
        async with aiohttp.ClientSession() as session:
            from .fetcher import fetch_single
            import asyncio
            tasks = [fetch_single(session, ch) for ch in channels]
            results: list[ChannelResult] = []
            for r in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(r, ChannelResult):
                    results.append(r)
                else:
                    logger.error("  [!] 异常: %s", r)
            return results

    async def fetch_channel(self, channel_id: str) -> ChannelResult:
        """请求单个频道。"""
        from .fetcher import fetch_single
        async with aiohttp.ClientSession() as session:
            return await fetch_single(session, {"channel_id": channel_id})
