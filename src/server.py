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
from .proxy.relay import create_app, update_channel_urls, register_hup_reload
from .tunnel import start_tunnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------
# 频道加载
# ---------------------------------------------------------------

def load_channels() -> tuple[list[dict], list[dict]]:
    """加载 channels.json，返回 (mgtv_channels, static_channels)。"""
    if not settings.channels_file.exists():
        logger.error("[!] channels.json 不存在: %s", settings.channels_file)
        return [], []
    with open(settings.channels_file, encoding="utf-8") as f:
        data = json.load(f)

    all_channels = [c for c in data.get("channels", []) if not c.get("offline")]
    mgtv_channels = [c for c in all_channels if c.get("source") != "static"]
    static_channels = [c for c in all_channels if c.get("source") == "static"]
    return mgtv_channels, static_channels


def load_static_channel_results(static_channels: list[dict]) -> list:
    """将 static 频道转换为 ChannelResult 格式。"""
    from .api.fetcher import ChannelResult
    results = []
    for ch in static_channels:
        results.append(ChannelResult(
            channel_id=ch["channel_id"],
            name=ch["name"],
            logo=ch.get("logo", ""),
            url=ch.get("url", ""),
            ok=bool(ch.get("url")),
            error="" if ch.get("url") else "static channel missing url",
            group=ch.get("group", "湖南"),
        ))
    return results


# ---------------------------------------------------------------
# 启动时静态 URL 可用性检查
# ---------------------------------------------------------------

async def check_static_urls(static_channels: list[dict], timeout: int = 10) -> dict[str, bool]:
    """并发检查 static 频道的 URL 是否可用。

    Returns:
        {channel_id: is_reachable}
    """
    import aiohttp
    results: dict[str, bool] = {}

    async def check_one(ch: dict) -> tuple[str, bool]:
        url = ch.get("url", "")
        if not url:
            return ch["channel_id"], False
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.head(url, timeout=aiohttp.ClientTimeout(total=timeout), ssl=True) as resp:
                    ok = resp.status < 400
                    return ch["channel_id"], ok
        except Exception:
            return ch["channel_id"], False

    if not static_channels:
        return results

    tasks = [check_one(ch) for ch in static_channels]
    for cid, ok in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(cid, tuple):
            results[cid[0]] = cid[1]
        elif isinstance(cid, Exception):
            pass

    return results


async def fetch_and_update(client: MgtvClient, tunnel_domain: str) -> list:
    """获取所有频道 URL，生成 m3u，写入 proxy 缓存。"""
    mgtv_channels, static_channels = load_channels()
    results = []

    # MGTV 频道走 API
    if mgtv_channels:
        mgtv_results = await client.fetch_all(mgtv_channels)
        results.extend(mgtv_results)

    # Static 频道直接使用 JSON 中的 url
    static_results = load_static_channel_results(static_channels)
    results.extend(static_results)

    ok_results = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    logger.info("刷新完成: 成功 %d/%d", len(ok_results), len(results))
    for r in failed:
        logger.warning("  失败: %s - %s", r.name, r.error)

    base_url = f"https://{tunnel_domain}" if tunnel_domain else f"http://localhost:{settings.server_port}"

    # 生成聚合 m3u
    m3u_path = Path(__file__).parent.parent / "mgtv.m3u"
    M3uGenerator().generate_file(ok_results, base_url, m3u_path)
    logger.info("m3u 已写入: %s", m3u_path)

    # 生成单频道 m3u8 文件（每频道一个文件）
    await generate_single_m3u8(ok_results, base_url)

    return ok_results


async def generate_single_m3u8(results: list, base_url: str) -> None:
    """为每个频道生成独立的 .m3u8 文件到 m3u8/ 目录。"""
    out_dir = Path(__file__).parent.parent / "m3u8"
    out_dir.mkdir(exist_ok=True)

    for r in results:
        if not r.ok:
            continue
        live_url = f"{base_url}/live/{r.channel_id}.flv"
        lines = [
            "#EXTM3U",
            f"#EXTINF:-1 tvg-id=\"{r.channel_id}\" "
            f'tvg-name="{r.name}" '
            f'tvg-logo="{r.logo}" '
            f'group-title="{r.group}",{r.name}',
            live_url,
            "",
        ]
        out_file = out_dir / f"{r.channel_id}.m3u8"
        out_file.write_text("\n".join(lines), encoding="utf-8")

    logger.info("单频道 m3u8 已写入: %s/*.m3u8 (%d 个)", out_dir, len(results))


async def periodic_refresh(client: MgtvClient, tunnel_domain: str, interval_minutes: int):
    """定时刷新任务。"""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await fetch_and_update(client, tunnel_domain)
        except Exception as e:
            logger.error("定时刷新失败: %s", e)


# ---------------------------------------------------------------
# SIGHUP 热重载
# ---------------------------------------------------------------

async def reload_channels() -> None:
    """SIGHUP 触发：重新加载频道，刷新 proxy URL 缓存，重新生成 m3u。"""
    logger.info("热重载: 重新加载 channels.json ...")
    client = MgtvClient()
    try:
        ok_results = await fetch_and_update(client, "")
        channel_urls = {r.channel_id: r.url for r in ok_results if r.ok}
        update_channel_urls(channel_urls)
        logger.info("热重载完成: %d 个频道", len(channel_urls))
    except Exception as e:
        logger.error("热重载失败: %s", e)


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

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

    # 4. 启动时检查 static URL 可用性
    _, static_channels = load_channels()
    if static_channels:
        logger.info("检查 static 频道可用性...")
        url_status = await check_static_urls(static_channels)
        bad = [cid for cid, ok in url_status.items() if not ok]
        if bad:
            logger.warning("  以下 static 频道 URL 不可达: %s", bad)
        else:
            logger.info("  所有 static 频道 URL 检查通过")

    # 5. 启动 proxy
    channel_urls = {r.channel_id: r.url for r in ok_results if r.ok}
    app = create_app(channel_urls)

    # 注册 SIGHUP 热重载
    register_hup_reload(lambda: asyncio.create_task(reload_channels()))

    # 6. 启动定时刷新
    refresh_task = asyncio.create_task(
        periodic_refresh(client, tunnel_domain, settings.fetch_interval_minutes)
    )

    # 7. 启动 web server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.server_host, settings.server_port)
    await site.start()
    logger.info("Proxy 启动: http://%s:%d", settings.server_host, settings.server_port)

    # 8. 优雅退出
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
