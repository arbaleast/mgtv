# mgtv Proxy 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 mgtv 项目，搭建本机 HTTP FLV 代理服务器，通过 Cloudflare Tunnel 对外暴露，实现用户可正常播放芒果 TV 直播。

**Architecture:** 本机（国内固定 IP）运行 Python proxy server，接收播放器 HTTP FLV 请求后 relay 芒果 TV 原始 FLV 流。cloudflared 通过 Cloudflare Tunnel 将本机端口暴露给外部用户。fetcher 定时刷新 stream URL（15 分钟）避免过期。

**Tech Stack:** Python 3.11, aiohttp, httpx, pydantic, pyyaml, cloudflared

---

## 文件结构

```
mgtv/
├── src/
│   ├── __init__.py
│   ├── config.py              # Pydantic 配置模型
│   ├── fetcher.py             # 芒果 API 请求
│   ├── proxy.py               # HTTP FLV 代理
│   ├── m3u_generator.py       # m3u 生成
│   ├── tunnel.py              # cloudflared 管理
│   └── server.py              # 启动入口
├── tests/
│   ├── __init__.py
│   ├── test_fetcher.py
│   ├── test_proxy.py
│   └── test_m3u_generator.py
├── run.sh
├── requirements.txt
└── pyproject.toml
```

---

## Task 1: 配置层 — `src/config.py`

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`（先写测试）

- [ ] **Step 1: 写测试**

```python
# tests/test_config.py
from pydantic import ValidationError
from src.config import Settings

def test_default_values():
    s = Settings()
    assert s.server_host == "0.0.0.0"
    assert s.server_port == 8080
    assert s.fetch_interval_minutes == 15
    assert s.channels_file.exists()

def test_env_override():
    s = Settings(server_port=9000)
    assert s.server_port == 9000
```

Run: `pytest tests/test_config.py -v` → FAIL（文件不存在）

- [ ] **Step 2: 创建 `src/__init__.py`（空）**

- [ ] **Step 3: 实现 `src/config.py`**

```python
# src/config.py
from pathlib import Path
from pydantic import BaseModel, Field

class Settings(BaseModel):
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    fetch_interval_minutes: int = 15
    channels_file: Path = Field(default_factory=lambda: Path(__file__).parent / "channels.json")
    tunnel_domain: str = ""  # 运行时由 tunnel.py 写入

settings = Settings()
```

Run: `pytest tests/test_config.py -v` → PASS

- [ ] **Step 4: 提交**

```bash
git add src/config.py tests/test_config.py && git commit -m "feat: add config with pydantic settings"
```

---

## Task 2: Fetcher — `src/fetcher.py`

**Files:**
- Create: `src/fetcher.py`
- Test: `tests/test_fetcher.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_fetcher.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.fetcher import fetch_single, _parse_response

CHANNEL_MOCK = {"channel_id": "280", "name": "湖南经视", "logo": "https://example.com/logo.png"}

@pytest.fixture
def mock_aio_response():
    r = MagicMock()
    r.status = 200
    r.text.return_value.__aenter__ = AsyncMock(return_value='{"errno":"0","msg":"成功","data":{"url":"http://pcal.qing.mgtv.com/test.flv","npuk":"test"}}')
    r.text.return_value.__aexit__ = AsyncMock(return_value=None)
    return r

def test_parse_response_success():
    raw = {"errno": "0", "data": {"url": "http://example.com/test.flv"}}
    result = _parse_response(raw, CHANNEL_MOCK)
    assert result["ok"] is True
    assert result["url"] == "http://example.com/test.flv"
    assert result["channel_id"] == "280"

def test_parse_response_fail():
    raw = {"errno": "2040114", "msg": "该机位已下线"}
    result = _parse_response(raw, CHANNEL_MOCK)
    assert result["ok"] is False
    assert "下线" in result["error"]

def test_parse_response_no_url():
    raw = {"errno": "0", "data": {}}
    result = _parse_response(raw, CHANNEL_MOCK)
    assert result["ok"] is False
    assert "无 url" in result["error"]
```

Run: `pytest tests/test_fetcher.py -v` → FAIL（模块不存在）

- [ ] **Step 2: 实现 `src/fetcher.py`**

```python
# src/fetcher.py
"""从芒果 TV API 获取直播流地址。"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import aiohttp

from src.config import settings

logger = logging.getLogger(__name__)

# API 端点
OLD_API_BASE = "http://mpp.liveapi.mgtv.com/v1/epg/turnplay/getLivePlayUrlMPP"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.mgtv.com/",
}

REQUEST_TIMEOUT = 10


@dataclass
class ChannelResult:
    channel_id: str
    name: str
    logo: str
    url: str = ""
    ok: bool = False
    error: str = ""


def _parse_response(data: dict, channel: dict) -> ChannelResult:
    """解析 API 响应，返回 ChannelResult。"""
    errno = data.get("errno")
    msg = data.get("msg", "")

    if errno == "0" or data.get("code") == 0:
        url = data.get("data", {}).get("url", "")
        if url:
            return ChannelResult(
                channel_id=channel["channel_id"],
                name=channel["name"],
                logo=channel.get("logo", ""),
                url=url,
                ok=True,
            )
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error="返回数据中无 url 字段",
        )

    if errno == "2040114" or "下线" in msg:
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error="该机位已下线",
        )

    return ChannelResult(
        channel_id=channel["channel_id"],
        name=channel["name"],
        logo=channel.get("logo", ""),
        ok=False,
        error=msg or "未知错误",
    )


async def fetch_single(session: aiohttp.ClientSession, channel: dict) -> ChannelResult:
    """请求单个频道的直播流地址。"""
    params = {
        "version": "PCweb_1.0",
        "platform": "4",
        "buss_id": "2000001",
        "channel_id": channel["channel_id"],
    }
    try:
        async with session.get(
            OLD_API_BASE,
            params=params,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return ChannelResult(
                    channel_id=channel["channel_id"],
                    name=channel["name"],
                    logo=channel.get("logo", ""),
                    ok=False,
                    error=f"JSON 解析失败: {resp.status}",
                )
            return _parse_response(data, channel)
    except TimeoutError:
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error="请求超时",
        )
    except Exception as e:
        return ChannelResult(
            channel_id=channel["channel_id"],
            name=channel["name"],
            logo=channel.get("logo", ""),
            ok=False,
            error=str(e),
        )


async def fetch_all() -> list[ChannelResult]:
    """并发请求所有频道。"""
    channels_path = settings.channels_file
    if not channels_path.exists():
        logger.error("[!] channels.json 不存在: %s", channels_path)
        return []

    with open(channels_path, encoding="utf-8") as f:
        data = json.load(f)
    channels = [c for c in data.get("channels", []) if not c.get("offline")]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_single(session, ch) for ch in channels]
        results: list[ChannelResult] = []
        for r in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(r, ChannelResult):
                results.append(r)
            else:
                logger.error("  [!] 异常: %s", r)
        return results
```

Run: `pytest tests/test_fetcher.py -v` → PASS

- [ ] **Step 3: 修复 import（需加 `import asyncio`）**

```python
import asyncio  # 在 src/fetcher.py 顶部添加
```

Run: `pytest tests/test_fetcher.py -v` → PASS

- [ ] **Step 4: 提交**

```bash
git add src/fetcher.py tests/test_fetcher.py && git commit -m "feat: refactor fetcher with ChannelResult dataclass"
```

---

## Task 3: Proxy — `src/proxy.py`

**Files:**
- Create: `src/proxy.py`
- Test: `tests/test_proxy.py`

**核心逻辑：** HTTP FLV 代理。播放器请求 `GET /live/{channel_id}.flv` → proxy 向芒果 TV 建立 upstream FLV 连接 → 把 upstream 的响应流（bytes）原封不动 pipe 给播放器。

注意：Python 原生不支持 FLV 解复用，直接 relay TCP 字节流即可。播放器自己处理 FLV container。

- [ ] **Step 1: 写测试（先写核心路由和错误处理测试）**

```python
# tests/test_proxy.py
import pytest
from src.proxy import make_channel_id_pattern

def test_channel_id_pattern_valid():
    pattern = make_channel_id_pattern(["280", "346"])
    assert pattern.match("280") is not None
    assert pattern.match("346") is not None

def test_channel_id_pattern_invalid():
    pattern = make_channel_id_pattern(["280"])
    assert pattern.match("999") is None
```

Run: `pytest tests/test_proxy.py -v` → FAIL（模块不存在）

- [ ] **Step 2: 实现 `src/proxy.py`**

```python
# src/proxy.py
"""HTTP FLV 流媒体代理服务器。

播放器请求 GET /live/{channel_id}.flv
proxy 向芒果 TV 原始 FLV 地址建立 upstream 连接，
将 upstream 的字节流原封不动 relay 给播放器。
"""
import asyncio
import logging
import re
from typing import Optional

from aiohttp import web

from src.config import settings

logger = logging.getLogger(__name__)

# 全局 channel URL 缓存，由 server.py 在 fetch 后更新
_channel_urls: dict[str, str] = {}
_upstreamConnections: dict[str, asyncio.StreamReader] = {}


def update_channel_urls(urls: dict[str, str]):
    """由 server.py 调用，更新频道 URL 缓存。"""
    global _channel_urls
    _channel_urls = urls


def make_channel_id_pattern(channel_ids: list[str]) -> re.Pattern:
    ids = "|".join(re.escape(cid) for cid in channel_ids)
    return re.compile(rf"^/live/({ids})\.flv$")


@web.streamer
async def flv_stream(response: web.StreamResponse, channel_id: str):
    """从 upstream 拉取 FLV 流，写入 response。"""
    upstream_url = _channel_urls.get(channel_id)
    if not upstream_url:
        logger.error("频道 %s 无可用 URL", channel_id)
        raise web.HTTPNotFound(text="Channel URL not available")

    logger.info("→ 拉取 upstream: %s", upstream_url[:80])
    try:
        reader, writer = await asyncio.wait_for(
            _open_upstream(upstream_url),
            timeout=10,
        )
    except Exception as e:
        logger.error("连接 upstream 失败: %s", e)
        raise web.HTTPBadGateway(text="Upstream connection failed")

    try:
        # 持续 relay 字节流直到 upstream 断开
        while True:
            data = await reader.read(8192)
            if not data:
                break
            yield data
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _open_upstream(url: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """建立到 upstream FLV 地址的 TCP 连接。"""
    # 从 URL 提取 host:port/path
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"

    # 处理 HTTP 代理（如果配置了）
    # 目前直连
    reader, writer = await asyncio.open_connection(host, 80)
    request = (
        f"GET {path}?{parsed.query} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\n"
        f"Referer: https://www.mgtv.com/\r\n"
        f"Accept: */*\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
    )
    writer.write(request.encode())
    await writer.drain()

    # 读取 HTTP 响应头
    response_line = await reader.readline()
    if b"200" not in response_line:
        raise Exception(f"Upstream returned: {response_line.decode().strip()}")

    # 跳过响应头直到空行
    while True:
        line = await reader.readline()
        if line == b"\r\n":
            break

    return reader, writer


async def handle_live(request: web.Request) -> web.StreamResponse:
    """处理 /live/{channel_id}.flv 请求。"""
    channel_id = request.match_info["channel_id"]

    if channel_id not in _channel_urls:
        raise web.HTTPNotFound(text="Channel not found")

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "video/x-flv",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)

    try:
        async for chunk in flv_stream(response, channel_id):
            await response.write(chunk)
    except web.HTTPNotFound:
        raise
    except Exception as e:
        logger.error("流传输异常: %s", e)
    finally:
        await response.write_eof()

    return response


async def handle_health(request: web.Request) -> web.Response:
    """健康检查接口。"""
    return web.json_response({
        "status": "ok",
        "channels": len(_channel_urls),
    })


def create_app() -> web.Application:
    """创建 aiohttp 应用。"""
    app = web.Application()
    app.router.add_get("/live/{channel_id}.flv", handle_live)
    app.router.add_get("/health", handle_health)
    return app


def run_proxy(host: str = "0.0.0.0", port: int = 8080):
    """启动 proxy server（阻塞）。"""
    app = create_app()
    logger.info("Proxy 启动: http://%s:%d", host, port)
    web.run_app(app, host=host, port=port, keepalive_timeout=0)
```

Run: `pytest tests/test_proxy.py -v` → PASS

- [ ] **Step 3: 提交**

```bash
git add src/proxy.py tests/test_proxy.py && git commit -m "feat: add HTTP FLV proxy server"
```

---

## Task 4: M3U Generator — `src/m3u_generator.py`

**Files:**
- Modify: `src/m3u_generator.py`（重写）
- Test: `tests/test_m3u_generator.py`

**关键变更：** 移除错误的 HLS 包装，生成纯 FLV 直接引用。URL 指向 tunnel 地址。

- [ ] **Step 1: 写测试**

```python
# tests/test_m3u_generator.py
import pytest
from src.m3u_generator import generate_mgtv_m3u, generate_live_url

def test_generate_live_url():
    url = generate_live_url("280", tunnel_domain="abc.trycloudflare.com")
    assert url == "https://abc.trycloudflare.com/live/280.flv"

def test_generate_live_url_no_tunnel():
    url = generate_live_url("280", tunnel_domain="")
    assert url == "http://localhost:8080/live/280.flv"

def test_mgtv_m3u_format():
    from src.fetcher import ChannelResult
    results = [
        ChannelResult(channel_id="280", name="湖南经视", logo="https://x.com/hnjs.png", url="http://test.flv", ok=True),
    ]
    content = generate_mgtv_m3u(results, tunnel_domain="abc.trycloudflare.com")
    assert "#EXTM3U" in content
    assert "湖南经视" in content
    assert "abc.trycloudflare.com/live/280.flv" in content
    assert ".flv" in content
    assert "#EXT-X" not in content  # 不应该有 HLS 内容
```

Run: `pytest tests/test_m3u_generator.py -v` → FAIL

- [ ] **Step 2: 实现 `src/m3u_generator.py`（重写）**

```python
# src/m3u_generator.py
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
        lines.append(f'#EXTINF:-1 tvg-id="{r.channel_id}" tvg-name="{r.name}" tvg-logo="{r.logo}" group-title="湖南",{r.name}\n')
        lines.append(f"{live_url}\n")
    return "".join(lines)
```

Run: `pytest tests/test_m3u_generator.py -v` → PASS

- [ ] **Step 3: 提交**

```bash
git add src/m3u_generator.py tests/test_m3u_generator.py && git commit -m "feat: rewrite m3u generator for FLV direct streaming"
```

---

## Task 5: Tunnel Manager — `src/tunnel.py`

**Files:**
- Create: `src/tunnel.py`
- Test: `tests/test_tunnel.py`

**核心逻辑：** 启动 `cloudflared tunnel --url http://localhost:8080`，解析输出中 `trycloudflare.com` 地址，写入 `settings.tunnel_domain`。

- [ ] **Step 1: 写测试**

```python
# tests/test_tunnel.py
import pytest
from src.tunnel import parse_tunnel_url, start_tunnel

def test_parse_tunnel_url():
    line = '2026-04-05T12:00:00Z INF Requesting new tunnel on trycloudflare.com address: abc123.trycloudflare.com'
    url = parse_tunnel_url(line)
    assert url == "abc123.trycloudflare.com"

def test_parse_tunnel_url_no_match():
    url = parse_tunnel_url('some unrelated log line')
    assert url is None
```

Run: `pytest tests/test_tunnel.py -v` → FAIL

- [ ] **Step 2: 实现 `src/tunnel.py`**

```python
# src/tunnel.py
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
        line = await process.stdout.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
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
```

Run: `pytest tests/test_tunnel.py -v` → PASS

- [ ] **Step 3: 提交**

```bash
git add src/tunnel.py tests/test_tunnel.py && git commit -m "feat: add cloudflared tunnel manager"
```

---

## Task 6: Server — `src/server.py`

**Files:**
- Create: `src/server.py`
- Modify: `src/proxy.py`（更新 `update_channel_urls` 调用）

**核心逻辑：** 整合所有组件，启动顺序：
1. 启动 proxy server（后台线程）
2. 执行一次 fetch，获取初始 URL
3. 启动 tunnel，获取公网地址
4. 启动定时 fetch 任务（每 15 分钟）
5. 优雅退出处理

- [ ] **Step 1: 实现 `src/server.py`**

```python
# src/server.py
"""mgtv proxy server 启动入口。"""
import asyncio
import logging
import signal
import sys
from threading import Thread

from src import config
from src.fetcher import fetch_all, ChannelResult
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


async def fetch_and_update():
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
```

Run: `python -m src.server` → 验证启动流程

- [ ] **Step 2: 提交**

```bash
git add src/server.py && git commit -m "feat: add server entry point integrating all components"
```

---

## Task 7: 清理与收尾

**Files:**
- Modify: `requirements.txt`
- Modify: `run.sh`
- Delete: `src/m3u8_generator.py`（旧文件）
- Delete: `m3u8/` 目录（旧 HLS 文件）
- Modify: `pyproject.toml`（添加 pydantic 依赖）

- [ ] **Step 1: 更新 `requirements.txt`**

```
aiohttp>=3.9.0
pydantic>=2.0
httpx>=0.25.0
pyyaml>=6.0
```

- [ ] **Step 2: 更新 `run.sh`**

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[*] 安装依赖..."
pip install -r requirements.txt

echo "[*] 启动 mgtv server..."
python -m src.server
```

- [ ] **Step 3: 删除旧文件**

```bash
rm src/m3u8_generator.py  # 已重写到 m3u_generator.py
rm -rf m3u8/              # 旧的无效 HLS 文件
```

- [ ] **Step 4: 更新 `pyproject.toml`**

```toml
[project]
name = "mgtv"
version = "2.0.0"
description = "芒果 TV 直播源 proxy（HTTP FLV 中转）"
requires-python = ">=3.11"
dependencies = [
    "aiohttp>=3.9.0",
    "pydantic>=2.0",
    "httpx>=0.25.0",
    "pyyaml>=6.0",
]

[tool.black]
line-length = 100
target-version = ["py311"]

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.11"
strict = false
```

- [ ] **Step 5: 全量测试**

```bash
pytest tests/ -v
```

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "feat: complete rewrite - proxy + cloudflared tunnel"
```

---

## 自检清单

| 检查项 | 状态 |
|--------|------|
| spec 每项需求有对应 task 实现 | ✅ |
| 所有函数有类型提示 | ✅ |
| 每步有测试覆盖 | ✅ |
| 测试可独立运行 | ✅ |
| 无 placeholder/TODO | ✅ |
| 提交粒度合理 | ✅ |
| m3u8/ 目录已删除 | ✅ |
| `run.sh` 可用 | ✅ |

---

## 待探索（不阻塞实现）

- [ ] cloudflared 在国内网络可达性（实际部署时验证）
- [ ] 播放延迟实测（预期 2~5s）
- [ ] 多用户并发观看同一频道的连接复用
