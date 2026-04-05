"""mgtv proxy server 启动入口。"""
import asyncio
import json
import logging
import signal
from pathlib import Path

from aiohttp import web

from .api.client import MgtvClient
from .config import settings
from .generator.m3u import M3uGenerator
from .proxy.routes import create_app
from .tunnel import start_tunnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_channels() -> list[dict]:
    """加载 channels.json。"""
    if not settings.channels_file.exists():
        logger.error("[!] channels.json 不存在: %s", settings.channels_file)
        return []
    with open(settings.channels_file, encoding="utf-8") as f:
        data = json.load(f)
    return [c for c in data.get("channels", []) if not c.get("offline")]


async def fetch_and_update(client: MgtvClient, tunnel_domain: str) -> list:
    """获取所有频道 URL，生成 m3u，写入 proxy 缓存。"""
    channels = load_channels()
    results = await client.fetch_all(channels)
    ok_results = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    logger.info("刷新完成: 成功 %d/%d", len(ok_results), len(results))
    for r in failed:
        logger.warning("  失败: %s - %s", r.name, r.error)

    base_url = f"https://{tunnel_domain}" if tunnel_domain else f"http://localhost:{settings.server_port}"
    m3u_path = Path(__file__).parent.parent / "mgtv.m3u"
    M3uGenerator().generate_file(ok_results, base_url, m3u_path)
    logger.info("m3u 已写入: %s", m3u_path)

    return ok_results


async def periodic_refresh(client: MgtvClient, tunnel_domain: str, interval_minutes: int):
    """定时刷新任务。"""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await fetch_and_update(client, tunnel_domain)
        except Exception as e:
            logger.error("定时刷新失败: %s", e)


async def main():
    client = MgtvClient()

    # 1. 初始 fetch（tunnel 未启动时用 localhost）
    await fetch_and_update(client, "")

    # 2. 启动 cloudflared tunnel
    logger.info("启动 cloudflared tunnel -> localhost:%d", settings.server_port)
    tunnel_process, tunnel_domain = await start_tunnel(settings.server_port)
    logger.info("=" * 50)
    logger.info("公网访问地址: https://%s", tunnel_domain)
    logger.info("本地访问地址: http://localhost:%d", settings.server_port)
    logger.info("=" * 50)

    # 3. 用真实 tunnel 地址更新 m3u
    ok_results = await fetch_and_update(client, tunnel_domain)

    # 4. 启动 proxy
    channel_urls = {r.channel_id: r.url for r in ok_results if r.ok}
    app = create_app(channel_urls)

    # 5. 启动定时刷新
    refresh_task = asyncio.create_task(
        periodic_refresh(client, tunnel_domain, settings.fetch_interval_minutes)
    )

    # 6. 启动 web server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.server_host, settings.server_port)
    await site.start()
    logger.info("Proxy 启动: http://%s:%d", settings.server_host, settings.server_port)

    # 7. 优雅退出
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    logger.info("关闭服务...")
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    tunnel_process.terminate()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
