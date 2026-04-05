"""HTTP FLV 流媒体代理服务器。

播放器请求 GET /live/{channel_id}.flv
proxy 向芒果 TV 原始 FLV 地址建立 upstream 连接，
将 upstream 的字节流原封不动 relay 给播放器。
"""
import asyncio
import logging
import re
from typing import Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# 全局 channel URL 缓存，由 server.py 在 fetch 后更新
_channel_urls: dict[str, str] = {}


def update_channel_urls(urls: dict[str, str]):
    """由 server.py 调用，更新频道 URL 缓存。"""
    global _channel_urls
    _channel_urls = urls


def make_channel_id_pattern(channel_ids: list[str]) -> re.Pattern:
    ids = "|".join(re.escape(cid) for cid in channel_ids)
    return re.compile(rf"^/live/({ids})\.flv$")


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


async def handle_live(request: web.Request) -> web.StreamResponse:
    """处理 /live/{channel_id}.flv 请求。"""
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


async def handle_health(request: web.Request) -> web.Response:
    """健康检查接口。"""
    return web.json_response({
        "status": "ok",
        "channels": len(_channel_urls),
    })


async def handle_mgtv_m3u(request: web.Request) -> web.Response:
    """提供 m3u 订阅文件。"""
    from pathlib import Path
    m3u_path = Path(__file__).parent / "mgtv.m3u"
    if m3u_path.exists():
        content = m3u_path.read_text(encoding="utf-8")
        return web.Response(text=content, content_type="application/vnd.apple.mpegurl")
    raise web.HTTPNotFound(text="mgtv.m3u not found")


def create_app() -> web.Application:
    """创建 aiohttp 应用。"""
    app = web.Application()
    app.router.add_get("/mgtv.m3u", handle_mgtv_m3u)
    app.router.add_get("/live/{channel_id}.flv", handle_live)
    app.router.add_get("/health", handle_health)
    return app


def run_proxy(host: str = "0.0.0.0", port: int = 8080):
    """启动 proxy server（阻塞）。"""
    app = create_app()
    logger.info("Proxy 启动: http://%s:%d", host, port)
    web.run_app(app, host=host, port=port, keepalive_timeout=0)
