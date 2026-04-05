"""aiohttp 路由注册。"""
from aiohttp import web
from .relay import relay_flv, update_channel_urls, _channel_urls


async def handle_mgtv_m3u(request: web.Request) -> web.Response:
    """提供 m3u 订阅文件。"""
    from pathlib import Path
    m3u_path = Path(__file__).parent.parent / "mgtv.m3u"
    if m3u_path.exists():
        content = m3u_path.read_text(encoding="utf-8")
        return web.Response(text=content, content_type="application/vnd.apple.mpegurl")
    raise web.HTTPNotFound(text="mgtv.m3u not found")


async def handle_health(request: web.Request) -> web.Response:
    """健康检查。"""
    return web.json_response({
        "status": "ok",
        "channels": len(_channel_urls),
    })


def create_app(channel_urls: dict[str, str]) -> web.Application:
    """创建 aiohttp 应用，注册路由。"""
    app = web.Application()
    update_channel_urls(channel_urls)
    app.router.add_get("/mgtv.m3u", handle_mgtv_m3u)
    app.router.add_get("/live/{channel_id}.flv", relay_flv)
    app.router.add_get("/health", handle_health)
    return app
