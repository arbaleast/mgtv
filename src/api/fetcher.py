"""从芒果 TV API 获取直播流地址。"""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp

from ..config import settings

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# API 端点
OLD_API_BASE = "http://mpp.liveapi.mgtv.com/v1/epg/turnplay/getLivePlayUrlMPP"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.mgtv.com/",
}

REQUEST_TIMEOUT = 10


@dataclass
class ChannelResult:
    """单个频道的抓取结果。"""
    channel_id: str
    name: str
    logo: str = ""
    url: str = ""
    ok: bool = False
    error: str = ""


def _parse_response(data: dict, channel: dict) -> ChannelResult:
    """解析 API 响应，返回 ChannelResult。"""
    errno = data.get("errno")
    msg = data.get("msg", "")

    if errno == "0" or data.get("code") == 0:
        url = data.get("data", {}).get("url", "")
        if url:
            return ChannelResult(
                channel_id=channel["channel_id"],
                name=channel["name"],
                logo=channel.get("logo", ""),
                url=url,
                ok=True,
            )
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error="返回数据中无 url 字段",
        )

    if errno == "2040114" or "下线" in msg:
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error="该机位已下线",
        )

    return ChannelResult(
        channel_id=channel["channel_id"],
        name=channel["name"],
        logo=channel.get("logo", ""),
        ok=False,
        error=msg or "未知错误",
    )


async def fetch_single(session: aiohttp.ClientSession, channel: dict) -> ChannelResult:
    """请求单个频道的直播流地址。"""
    params = {
        "version": "PCweb_1.0",
        "platform": "4",
        "buss_id": "2000001",
        "channel_id": channel["channel_id"],
    }
    try:
        async with session.get(
            OLD_API_BASE,
            params=params,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return ChannelResult(
                    channel_id=channel["channel_id"],
                    name=channel["name"],
                    logo=channel.get("logo", ""),
                    ok=False,
                    error=f"JSON 解析失败: {resp.status}",
                )
            return _parse_response(data, channel)
    except TimeoutError:
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error="请求超时",
        )
    except Exception as e:
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error=str(e),
        )


async def fetch_all(channels: list[dict]) -> list[ChannelResult]:
    """并发请求所有频道。"""
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_single(session, ch) for ch in channels]
        results: list[ChannelResult] = []
        for r in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(r, ChannelResult):
                results.append(r)
            else:
                logger.error("  [!] 异常: %s", r)
        return results
