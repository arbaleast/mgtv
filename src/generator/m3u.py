"""m3u 播放列表生成器。"""
from pathlib import Path
from typing import TYPE_CHECKING

from ..api.fetcher import ChannelResult

if TYPE_CHECKING:
    pass

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
            f'group-title="{r.group}",{r.name}\n'
        )
        lines.append(f"{live_url}\n")
    return "".join(lines)


class M3uGenerator:
    """m3u 播放列表生成器。"""

    def generate(self, results: list[ChannelResult], tunnel_domain: str) -> str:
        """生成 m3u 文本。"""
        return generate_mgtv_m3u(results, tunnel_domain)

    def generate_file(self, results: list[ChannelResult], tunnel_domain: str, output_path: "Path") -> None:
        """生成并写入 m3u 文件。"""
        content = self.generate(results, tunnel_domain)
        output_path.write_text(content, encoding="utf-8")
