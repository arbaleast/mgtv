"""生成 m3u 订阅文件。

芒果 TV 直播流为 HTTP-FLV 格式，直接引用 FLV 地址即可播放。
不再生成 m3u8 HLS 文件。
"""
import logging
from pathlib import Path

from src.fetcher import ChannelResult

logger = logging.getLogger(__name__)

M3U_HEADER = "#EXTM3U\n"


def generate_live_url(channel_id: str, tunnel_domain: str = "") -> str:
    """生成单个频道的播放地址。"""
    if tunnel_domain:
        return f"https://{tunnel_domain}/live/{channel_id}.flv"
    return f"http://localhost:8080/live/{channel_id}.flv"


def generate_mgtv_m3u(results: list[ChannelResult], tunnel_domain: str = "") -> str:
    """生成聚合 m3u 文件。"""
    lines = [M3U_HEADER]
    for r in results:
        if not r.ok or not r.url:
            continue
        live_url = generate_live_url(r.channel_id, tunnel_domain)
        lines.append(
            f"#EXTINF:-1 tvg-id=\"{r.channel_id}\" "
            f'tvg-name="{r.name}" '
            f'tvg-logo="{r.logo}" '
            f'group-title="湖南",{r.name}\n'
        )
        lines.append(f"{live_url}\n")
    return "".join(lines)


def generate_m3u8(channel_id: str, stream_url: str, logo: str = "") -> str:
    """生成单频道 m3u8 文件（保留兼容旧播放器）。"""
    lines = [
        M3U_HEADER,
        f"#EXTINF:-1 tvg-id=\"{channel_id}\" tvg-name=\"{channel_id}\" tvg-logo=\"{logo}\" group-title=\"湖南\",{channel_id}\n",
        f"{stream_url}\n",
    ]
    return "".join(lines)
