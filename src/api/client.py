from __future__ import annotations

import logging

from ..config import settings as _settings
from ..config import Settings
from .fetcher import fetch_all, ChannelResult

logger = logging.getLogger(__name__)


class MgtvClient:
    """芒果 TV API 客户端。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or _settings

    async def fetch_all(self, channels: list[dict]) -> list[ChannelResult]:
        """并发请求所有频道。"""
        return await fetch_all(channels)

    async def fetch_channel(self, channel_id: str) -> ChannelResult:
        """请求单个频道。"""
        from .fetcher import fetch_single
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                return await fetch_single(session, {"channel_id": channel_id})
            except Exception as e:
                logger.error("请求失败: %s", e)
                return ChannelResult(channel_id=channel_id, name="", ok=False, error=str(e))
