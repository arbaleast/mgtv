"""并发获取芒果 TV 直播流地址。

从旧 API 并发请求所有频道，生成 mgtv.m3u 和各频道独立文件。

Usage:
    python -m src.fetcher
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import config  # noqa: E402
from src.m3u8_generator import generate_m3u8  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


async def fetch_single(session: aiohttp.ClientSession, channel: dict) -> dict:
    """请求单个频道的直播流地址。"""
    params = {
        "version": "PCweb_1.0",
        "platform": "4",
        "buss_id": "2000001",
        "channel_id": channel["channel_id"],
    }
    try:
        async with session.get(
            config.OLD_API_BASE,
            params=params,
            headers=config.HEADERS,
            timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT),
        ) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return _fail(channel, f"JSON 解析失败: {resp.status}")

            # errno 是字符串 "0" 表示成功
            if data.get("errno") == "0" or data.get("code") == 0:
                url = (
                    data.get("data", {})
                    .get("url")
                )
                if url:
                    return _ok(channel, url)
                return _fail(channel, "返回数据中无 url 字段")
            # 频道下线
            if data.get("errno") == "2040114" or data.get("msg", "").find("下线") >= 0:
                return _fail(channel, "该机位已下线")
            return _fail(channel, data.get("msg", "未知错误"))
    except asyncio.TimeoutError:
        return _fail(channel, "请求超时")
    except Exception as e:
        return _fail(channel, str(e))


def _ok(channel: dict, url: str) -> dict:
    return {
        "channel_id": channel["channel_id"],
        "name": channel["name"],
        "logo": channel.get("logo", ""),
        "url": url,
        "ok": True,
    }


def _fail(channel: dict, reason: str) -> dict:
    return {
        "channel_id": channel["channel_id"],
        "name": channel["name"],
        "logo": channel.get("logo", ""),
        "url": "",
        "ok": False,
        "error": reason,
    }


async def fetch_all(channels: list[dict]) -> list[dict]:
    """并发请求所有频道，总耗时应接近最慢那一个。"""
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_single(session, ch) for ch in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    out = []
    for r in results:
        if isinstance(r, dict):
            out.append(r)
        else:
            log.error("  [!] 异常: %s", r)
    return out


async def main():
    channels_path = Path(__file__).parent / "channels.json"
    if not channels_path.exists():
        log.error("[!] channels.json 不存在: %s", channels_path)
        return

    with open(channels_path, encoding="utf-8") as f:
        data = json.load(f)
    channels = [c for c in data.get("channels", []) if not c.get("offline")]
    log.info("[*] 共 %d 个频道（已排除下线频道），开始并发请求...\n", len(channels))

    results = await fetch_all(channels)

    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]

    log.info("[+] 成功: %d/%d", len(ok), len(results))
    for r in ok:
        log.info("  %s: %s", r["name"], r["url"][:60] + "...")

    if fail:
        log.info("[!] 失败: %d 个", len(fail))
        for r in fail:
            log.info("  %s: %s", r["name"], r["error"])

    # 生成 m3u 文件
    generate_m3u8(ok)
    log.info("[*] 文件已生成: mgtv.m3u, m3u8/*.m3u8")


if __name__ == "__main__":
    asyncio.run(main())
