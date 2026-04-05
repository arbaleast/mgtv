"""HTTP FLV 流媒体代理核心逻辑。

relay FLV 流，不解码不修改。
"""
import asyncio
import logging
import re
from typing import Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# 全局 channel URL 缓存
_channel_urls: dict[str, str] = {}


def update_channel_urls(urls: dict[str, str]):
    """更新频道 URL 缓存。"""
    global _channel_urls
    _channel_urls = urls


async def _open_upstream(url: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """建立到 upstream FLV 地址的 TCP 连接。"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"

    reader, writer = await asyncio.open_connection(host, 80)
    request = (
        f"GET {path}?{parsed.query} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\n"
        f"Referer: https://www.mgtv.com/\r\n"
        f"Accept: */*\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
    )
    writer.write(request.encode())
    await writer.drain()

    # 读取 HTTP 响应头
    response_line = await reader.readline()
    if b"200" not in response_line:
        raise Exception(f"Upstream returned: {response_line.decode().strip()}")

    # 跳过响应头直到空行
    while True:
        line = await reader.readline()
        if line == b"\r\n":
            break

    return reader, writer


async def relay_flv(request: web.Request) -> web.StreamResponse:
    """处理 /live/{channel_id}.flv 请求，relay FLV 流。"""
    channel_id = request.match_info["channel_id"]

    if channel_id not in _channel_urls:
        raise web.HTTPNotFound(text="Channel not found")

    upstream_url = _channel_urls.get(channel_id)
    if not upstream_url:
        raise web.HTTPNotFound(text="Channel URL not available")

    logger.info("→ 拉取 upstream: %s", upstream_url[:80])
    try:
        reader, writer = await asyncio.wait_for(
            _open_upstream(upstream_url),
            timeout=10,
        )
    except Exception as e:
        logger.error("连接 upstream 失败: %s", e)
        raise web.HTTPBadGateway(text="Upstream connection failed")

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "video/x-flv",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)

    try:
        while True:
            data = await reader.read(8192)
            if not data:
                break
            await response.write(data)
    except ConnectionResetError:
        logger.warning("客户端断开连接")
    except Exception as e:
        logger.error("流传输异常: %s", e)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await response.write_eof()

    return response
