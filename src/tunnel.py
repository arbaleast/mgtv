"""cloudflared tunnel 进程管理。"""
import asyncio
import logging
import re
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

TUNNEL_CMD = "cloudflared"
TUNNEL_URL_RE = re.compile(r"trycloudflare\.com address:\s*(\S+)")


def is_cloudflared_installed() -> bool:
    return shutil.which(TUNNEL_CMD) is not None


def parse_tunnel_url(line: str) -> Optional[str]:
    """从 cloudflared 输出行解析 tunnel 公网地址。"""
    match = TUNNEL_URL_RE.search(line)
    return match.group(1) if match else None


async def start_tunnel(local_port: int = 8080) -> tuple[asyncio.subprocess.Process, str]:
    """启动 cloudflared tunnel，返回 (process, tunnel_domain)。"""
    if not is_cloudflared_installed():
        raise RuntimeError(
            "cloudflared 未安装。请运行: "
            "curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 "
            "-o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared"
        )

    logger.info("启动 cloudflared tunnel -> localhost:%d", local_port)
    process = await asyncio.create_subprocess_exec(
        TUNNEL_CMD, "tunnel", "--url", f"http://localhost:{local_port}",
        "--no-autoupdate",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    tunnel_domain: Optional[str] = None
    # 最多等 30 秒
    for _ in range(60):
        line_bytes = await process.stdout.readline()
        if not line_bytes:
            break
        decoded = line_bytes.decode("utf-8", errors="replace").strip()
        logger.debug("cloudflared: %s", decoded)
        domain = parse_tunnel_url(decoded)
        if domain:
            tunnel_domain = domain
            break
        await asyncio.sleep(0.5)

    if not tunnel_domain:
        process.terminate()
        raise RuntimeError("cloudflared tunnel 启动超时，未获取到公网地址")

    logger.info("Tunnel 已就绪: https://%s", tunnel_domain)
    return process, tunnel_domain
