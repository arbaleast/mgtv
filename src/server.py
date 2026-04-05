"""mgtv proxy server 启动入口。"""
import asyncio
import atexit
import logging
import re
import subprocess
import threading
from typing import Optional

from src import config
from src.fetcher import fetch_all
from src.m3u_generator import generate_mgtv_m3u
from src.proxy import update_channel_urls, run_proxy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_tunnel_process: Optional[subprocess.Popen] = None


def close_tunnel():
    global _tunnel_process
    if _tunnel_process:
        _tunnel_process.terminate()
        logger.info("Tunnel 已关闭")


atexit.register(close_tunnel)


def _read_tunnel_url(proc: subprocess.Popen, result: dict):
    """在线程中读取 cloudflared 输出，找到 tunnel URL。"""
    import time
    url_re = re.compile(rb"https://([a-zA-Z0-9-]+\.trycloudflare\.com)")
    buf = b""
    while True:
        chunk = proc.stdout.read(8192)
        if not chunk:
            break
        buf += chunk
        m = url_re.search(buf)
        if m:
            result["url"] = m.group(1).decode()
            return
        if len(buf) > 4096:
            buf = buf[-1024:]
        time.sleep(0.1)


def start_tunnel_subprocess(port: int) -> tuple[subprocess.Popen, str]:
    """启动 cloudflared tunnel，返回 (process, tunnel_domain)。"""
    import shutil
    cmd = shutil.which("cloudflared") or "/home/al/bin/cloudflared"
    proc = subprocess.Popen(
        [cmd, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )

    result = {}
    t = threading.Thread(target=_read_tunnel_url, args=(proc, result), daemon=True)
    t.start()

    t.join(timeout=60)
    if not result.get("url"):
        proc.terminate()
        raise RuntimeError("cloudflared tunnel 启动超时")

    tunnel_domain = result["url"]
    logger.info("Tunnel 已就绪: https://%s", tunnel_domain)
    return proc, tunnel_domain


async def fetch_and_update() -> list:
    """获取所有频道 URL，更新 proxy 缓存，写入 m3u 文件。"""
    results = await fetch_all()
    ok_results = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    logger.info("刷新完成: 成功 %d/%d", len(ok_results), len(results))
    for r in failed:
        logger.warning("  失败: %s - %s", r.name, r.error)

    url_map = {r.channel_id: r.url for r in ok_results}
    update_channel_urls(url_map)

    tunnel_domain = config.settings.tunnel_domain
    m3u_content = generate_mgtv_m3u(ok_results, tunnel_domain)
    m3u_path = config.settings.channels_file.parent / "mgtv.m3u"
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)
    logger.info("m3u 已写入: %s", m3u_path)

    return ok_results


async def periodic_fetch_async(interval_minutes: int, stop_event: asyncio.Event):
    """定时刷新任务。"""
    while not stop_event.is_set():
        await asyncio.sleep(interval_minutes * 60)
        if stop_event.is_set():
            break
        await fetch_and_update()


def run_asyncio_loop(interval_minutes: int, stop_event: asyncio.Event):
    """在线程中运行 asyncio 事件循环。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(periodic_fetch_async(interval_minutes, stop_event))
    finally:
        loop.close()


def main():
    global _tunnel_process
    settings = config.settings

    # 1. 初始 fetch
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_and_update())

    # 2. 启动 cloudflared tunnel
    logger.info("启动 cloudflared tunnel -> localhost:%d", settings.server_port)
    _tunnel_process, tunnel_domain = start_tunnel_subprocess(settings.server_port)
    settings.tunnel_domain = tunnel_domain
    logger.info("=" * 50)
    logger.info("公网访问地址: https://%s", tunnel_domain)
    logger.info("本地访问地址: http://localhost:%d", settings.server_port)
    logger.info("=" * 50)

    # 3. 用真实 tunnel 地址更新 m3u
    loop.run_until_complete(fetch_and_update())

    # 4. 启动定时刷新线程
    stop_event = asyncio.Event()
    fetch_thread = threading.Thread(
        target=run_asyncio_loop,
        args=(settings.fetch_interval_minutes, stop_event),
        daemon=True,
    )
    fetch_thread.start()

    # 5. 启动 proxy server（阻塞主线程）
    logger.info("Proxy 启动中...")
    try:
        run_proxy(settings.server_host, settings.server_port)
    finally:
        stop_event.set()
        close_tunnel()


if __name__ == "__main__":
    main()
