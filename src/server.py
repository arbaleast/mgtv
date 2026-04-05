"""mgtv proxy server 启动入口。"""
import asyncio
import logging
import signal
import sys
from threading import Thread

from src import config
from src.fetcher import fetch_all
from src.m3u_generator import generate_mgtv_m3u
from src.proxy import update_channel_urls, run_proxy
from src.tunnel import start_tunnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_running = True
_fetch_task: asyncio.Task | None = None


async def fetch_and_update() -> list:
    """获取所有频道 URL，更新 proxy 缓存，写入 m3u 文件。"""
    results = await fetch_all()
    ok_results = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    logger.info("刷新完成: 成功 %d/%d", len(ok_results), len(results))
    for r in failed:
        logger.warning("  失败: %s - %s", r.name, r.error)

    # 更新 proxy URL 缓存
    url_map = {r.channel_id: r.url for r in ok_results}
    update_channel_urls(url_map)

    # 生成 m3u 文件
    tunnel_domain = config.settings.tunnel_domain
    m3u_content = generate_mgtv_m3u(ok_results, tunnel_domain)
    m3u_path = config.settings.channels_file.parent / "mgtv.m3u"
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)
    logger.info("m3u 已写入: %s", m3u_path)

    return ok_results


async def periodic_fetch(interval_minutes: int):
    """定时刷新任务。"""
    while _running:
        await asyncio.sleep(interval_minutes * 60)
        if not _running:
            break
        await fetch_and_update()


async def main():
    global _fetch_task
    settings = config.settings

    # 1. 先执行一次 fetch（proxy 启动前先拿到 URL）
    await fetch_and_update()

    # 2. 在后台线程启动 proxy（阻塞）
    proxy_thread = Thread(target=run_proxy, kwargs={
        "host": settings.server_host,
        "port": settings.server_port,
    }, daemon=True)
    proxy_thread.start()
    logger.info("Proxy 服务已启动 (后台)")
    await asyncio.sleep(1)  # 等待 proxy 真正监听

    # 3. 启动 cloudflared tunnel
    _, tunnel_domain = await start_tunnel(settings.server_port)
    settings.tunnel_domain = tunnel_domain
    logger.info("=" * 50)
    logger.info("公网访问地址: https://%s", tunnel_domain)
    logger.info("本地访问地址: http://localhost:%d", settings.server_port)
    logger.info("=" * 50)

    # 4. 更新 m3u 文件（填入真实 tunnel 地址）
    await fetch_and_update()

    # 5. 启动定时刷新
    _fetch_task = asyncio.create_task(periodic_fetch(settings.fetch_interval_minutes))

    # 6. 等待信号退出
    loop = asyncio.get_event_loop()
    stop_event = loop.create_future()

    def on_signal():
        global _running
        _running = False
        stop_event.set_result(None)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, on_signal)

    await stop_event
    logger.info("收到退出信号，关闭中...")


if __name__ == "__main__":
    asyncio.run(main())
