#!/usr/bin/env python3
"""Standalone 脚本：从芒果 TV API 抓取频道 URL 并生成 m3u 文件。

用于 GitHub Actions 或本地手动执行。
不需要 cloudflared tunnel，纯生成文件。
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.client import MgtvClient
from src.api.fetcher import ChannelResult
from src.generator.m3u import M3uGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CHANNELS_FILE = PROJECT_ROOT / "src" / "channels.json"
OUTPUT_M3U = PROJECT_ROOT / "mgtv.m3u"


def load_channels() -> tuple[list[dict], list[dict]]:
    """加载 channels.json，返回 (mgtv_channels, static_channels)。"""
    if not CHANNELS_FILE.exists():
        raise FileNotFoundError(f"channels.json not found: {CHANNELS_FILE}")
    with open(CHANNELS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    all_channels = [c for c in data.get("channels", []) if not c.get("offline")]
    mgtv_channels = [c for c in all_channels if c.get("source") != "static"]
    static_channels = [c for c in all_channels if c.get("source") == "static"]
    return mgtv_channels, static_channels


def load_static_channel_results(static_channels: list[dict]) -> list[ChannelResult]:
    """将 static 频道转换为 ChannelResult。"""
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


async def main():
    mgtv_channels, static_channels = load_channels()
    logger.info("抓取中: MGTV=%d, Static=%d", len(mgtv_channels), len(static_channels))

    results: list[ChannelResult] = []

    # MGTV 频道走 API
    if mgtv_channels:
        client = MgtvClient()
        mgtv_results = await client.fetch_all(mgtv_channels)
        results.extend(mgtv_results)

    # Static 频道直接使用 JSON 中的 url
    static_results = load_static_channel_results(static_channels)
    results.extend(static_results)

    ok_results = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    logger.info("结果: 成功 %d/%d", len(ok_results), len(results))
    for r in failed:
        logger.warning("  失败: %s - %s", r.name, r.error)

    # 生成 m3u（无 tunnel，用占位 base_url，仅域名部分）
    M3uGenerator().generate_file(ok_results, "placeholder.example.com", OUTPUT_M3U)
    logger.info("m3u 已写入: %s", OUTPUT_M3U)

    # 生成单频道 m3u8
    out_dir = PROJECT_ROOT / "m3u8"
    out_dir.mkdir(exist_ok=True)
    for r in ok_results:
        if not r.ok:
            continue
        live_url = f"https://placeholder.example.com/live/{r.channel_id}.flv"
        lines = [
            "#EXTM3U",
            f'#EXTINF:-1 tvg-id="{r.channel_id}" tvg-name="{r.name}" tvg-logo="{r.logo}" group-title="{r.group}",{r.name}',
            live_url,
        ]
        (out_dir / f"{r.channel_id}.m3u8").write_text("\n".join(lines), encoding="utf-8")
    logger.info("单频道 m3u8 已写入: %s/", out_dir)


if __name__ == "__main__":
    asyncio.run(main())
