"""生成 m3u 播放列表文件。"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# M3U 头部，指向 EPG XML
M3U_HEADER = (
    '#EXTM3U x-tvg-url="https://mirror.ghproxy.com/'
    'https://raw.githubusercontent.com/arbaleast/mgtv/main/mgtv.xml"\n'
)


def sanitize(text: str) -> str:
    """去除不可用于 m3u 标签的字符。"""
    return re.sub(r"[,\n]", "", text)


def generate_m3u_header(channel: dict) -> str:
    """生成单个频道的 #EXTINF 行。"""
    return (
        f'#EXTINF:-1 tvg-id="{channel["channel_id"]}" '
        f'tvg-name="{sanitize(channel["name"])}" '
        f'tvg-logo="{channel.get("logo", "")}" '
        f'group-title="湖南",{channel["name"]} \n'
    )


def write_mgtv_m3u(results: list[dict]):
    """生成聚合 m3u 文件：mgtv.m3u"""
    lines = [M3U_HEADER]
    for r in results:
        if not r.get("url"):
            continue
        lines.append(generate_m3u_header(r))
        lines.append(r["url"] + "\n")

    content = "".join(lines)
    out_path = Path(__file__).parent.parent / "mgtv.m3u"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)


def write_channel_m3u8(result: dict):
    """生成单个频道的 m3u8 文件：m3u8/<hn##.m3u8>"""
    if not result.get("url"):
        return

    channel_id = result["channel_id"]
    index_map = {
        "280": "01", "346": "02", "484": "03", "261": "04",
        "229": "05", "344": "06", "267": "07", "578": "08",
        "316": "09", "287": "10", "218": "11", "329": "12",
        "269": "13", "254": "14", "230": "15",
    }
    seq = index_map.get(channel_id, channel_id)
    filename = f"hn{seq}.m3u8"
    out_path = Path(__file__).parent.parent / "m3u8" / filename

    lines = [
        "#EXTM3U\n",
        "#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1280000\n",
        result["url"] + "\n",
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))


def generate_m3u8(results: list[dict]):
    """生成所有 m3u 文件（聚合 + 各频道独立文件）。"""
    write_mgtv_m3u(results)
    for r in results:
        write_channel_m3u8(r)
