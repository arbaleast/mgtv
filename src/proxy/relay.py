"""HTTP FLV 流媒体代理核心逻辑。

relay FLV 流，不解码不修改。

功能清单：
- 播放量统计：内存计数 + 异步批量持久化（30s 刷盘）
- 健康指标：per-channel success/failure/last_ok
- 连接池复用：全局 TCPConnector，按 host 限制并发
- upstream 重试：超时/5xx 自动重试 3 次（指数退避）
- 速率限制：per-IP per-channel 10 req/s，超限返回 429
- 请求耗时日志：INFO 级别记录每个 relay 请求耗时
- stats 内存上限：最多保留 200 条记录，超出后清理最老的
- SIGHUP 热重载：收到信号时重新加载 channels.json
"""
import asyncio
import json
import logging
import signal
import time
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------
_channel_urls: dict[str, str] = {}
_channels_file: Path = Path(__file__).parent.parent / "channels.json"
STATS_FILE: Path = Path(__file__).parent.parent.parent / "stats.json"

# ---- 播放量统计（内存 + 异步持久化 + 上限）----
_stats_lock = asyncio.Lock()
_stats_cache: dict[str, int] = {}
_stats_dirty = False
_save_task: asyncio.Task | None = None
STATS_MAX_ENTRIES = 200          # 超过此数量时清理最老的 20%

# ---- 健康指标 ----
_health_lock = asyncio.Lock()
_health: dict[str, dict] = {}   # channel_id -> {"success": N, "failure": N, "last_ok": bool}

# ---- 连接池 ----
_connector: aiohttp.TCPConnector | None = None
_http_session: aiohttp.ClientSession | None = None

# ---- 速率限制：client_ip -> {channel_id -> [timestamp, ...]} ----
_rate_limit_lock = asyncio.Lock()
_rate_limit: dict[str, dict[str, list[float]]] = {}
RATE_LIMIT_REQ = 10    # 每秒最多请求次数
RATE_LIMIT_WINDOW = 1.0  # 时间窗口（秒）

# ---- 上游重试 ----
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.5  # 首次重试延迟（秒）


def _get_session() -> aiohttp.ClientSession:
    """获取或创建全局 HTTP session（延迟创建连接池）。"""
    global _http_session, _connector
    if _http_session is None or _http_session.closed:
        if _connector is None:
            _connector = aiohttp.TCPConnector(
                limit=50,
                limit_per_host=10,
                ttl_dns_cache=300,
                keepalive_timeout=30,
            )
        _http_session = aiohttp.ClientSession(connector=_connector)
    return _http_session


# ---------------------------------------------------------------
# Stats
# ---------------------------------------------------------------

def _load_stats() -> dict[str, int]:
    """从 stats.json 加载播放量统计（启动时一次性加载）。"""
    global _stats_cache
    if not STATS_FILE.exists():
        return {}
    try:
        with open(STATS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        _stats_cache = {k: int(v) for k, v in data.items()}
        return _stats_cache.copy()
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("stats.json 解析失败，重新初始化: %s", e)
        _stats_cache = {}
        return {}


async def _save_stats_async(stats: dict[str, int]) -> None:
    """异步原子写入 stats.json。"""
    tmp = STATS_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        tmp.replace(STATS_FILE)
    except Exception as e:
        logger.error("写入 stats.json 失败: %s", e)
        if tmp.exists():
            tmp.unlink(missing_ok=True)


async def _periodic_save() -> None:
    """定期（每 30s）将内存统计刷盘，后台运行。"""
    global _stats_dirty
    while True:
        await asyncio.sleep(30)
        async with _stats_lock:
            if not _stats_dirty:
                continue
            await _save_stats_async(_stats_cache.copy())
            _stats_dirty = False
            logger.debug("stats 已刷盘")


def _cap_stats() -> None:
    """stats 超过上限时清理最老的 20% 条目。"""
    global _stats_cache
    if len(_stats_cache) <= STATS_MAX_ENTRIES:
        return
    # 按计数值升序，删除最低的 20%
    sorted_items = sorted(_stats_cache.items(), key=lambda x: x[1])
    remove_count = max(1, len(sorted_items) // 5)
    for k, _ in sorted_items[:remove_count]:
        del _stats_cache[k]
    logger.info("stats 内存超限，清理了 %d 条低计数记录，剩余 %d", remove_count, len(_stats_cache))


def _increment_stat(channel_id: str) -> int:
    """对应 channel_id 播放量+1，内存操作，极快返回。"""
    global _stats_dirty
    if channel_id not in _stats_cache:
        _stats_cache[channel_id] = 0
    _stats_cache[channel_id] += 1
    _stats_dirty = True
    _cap_stats()
    return _stats_cache[channel_id]


def _warmed_health(urls: dict[str, str]) -> None:
    """预热健康指标：新增频道初始化记录，不影响已有数据。"""
    for cid in urls:
        if cid not in _health:
            _health[cid] = {"success": 0, "failure": 0, "last_ok": None}


def update_channel_urls(urls: dict[str, str]) -> None:
    """更新频道 URL 缓存。"""
    global _channel_urls
    _channel_urls = urls
    _warmed_health(urls)


# ---------------------------------------------------------------
# 速率限制
# ---------------------------------------------------------------

async def _check_rate_limit(client_ip: str, channel_id: str) -> bool:
    """检查 client_ip 对 channel_id 的请求是否超限。返回 True=允许，False=拒绝。"""
    now = time.time()
    async with _rate_limit_lock:
        ip_key = ip_bucket = client_ip
        if ip_bucket not in _rate_limit:
            _rate_limit[ip_bucket] = {}
        bucket = _rate_limit[ip_bucket]
        if channel_id not in bucket:
            bucket[channel_id] = []
        # 清理过期的请求记录
        cutoff = now - RATE_LIMIT_WINDOW
        bucket[channel_id] = [t for t in bucket[channel_id] if t > cutoff]
        if len(bucket[channel_id]) >= RATE_LIMIT_REQ:
            return False
        bucket[channel_id].append(now)
        return True


def _get_client_ip(request: web.Request) -> str:
    """优先从 X-Forwarded-For 取真实 IP，降级到 client_host。"""
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "")
        or request.remote or "unknown"
    )


# ---------------------------------------------------------------
# Upstream 请求（带重试）
# ---------------------------------------------------------------

async def _stream_upstream_with_retry(url: str, timeout: int = 30) -> aiohttp.ClientResponse:
    """带重试的 upstream 请求。

    超时或 5xx 响应时最多重试 MAX_RETRIES 次，
    退避策略：0.5s → 1s → 2s（指数退避）。
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)

    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            session = _get_session()
            async with session.get(
                url,
                headers=base_headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
                ssl=True,
            ) as resp:
                if resp.status == 200:
                    return resp
                # 非 200 且非重试次数用尽，尝试重试
                if attempt < MAX_RETRIES and resp.status >= 500:
                    last_exc = Exception(f"HTTP {resp.status}")
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning("upstream %s 返回 %d，%.1fs 后重试（%d/%d）",
                                   url[:80], resp.status, delay, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(delay)
                    continue
                raise Exception(f"Upstream returned: HTTP {resp.status}")
        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("upstream %s 超时，%.1fs 后重试（%d/%d）",
                               url[:80], delay, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(delay)
        except aiohttp.ClientError as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("upstream %s 连接失败 %s，%.1fs 后重试（%d/%d）",
                               url[:80], e, delay, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(delay)

    raise last_exc or Exception("upstream 请求失败")


# ---------------------------------------------------------------
# Relay handler
# ---------------------------------------------------------------

async def relay_flv(request: web.Request) -> web.StreamResponse:
    """处理 /live/{channel_id}.flv 请求，relay FLV/TS 流。"""
    start_ms = time.monotonic()
    channel_id = request.match_info["channel_id"]
    client_ip = _get_client_ip(request)

    # 速率限制检查
    if not await _check_rate_limit(client_ip, channel_id):
        logger.warning("[%s] 速率超限 %s", client_ip, channel_id)
        raise web.HTTPTooManyRequests(text="Rate limit exceeded, try again later.")

    if channel_id not in _channel_urls:
        raise web.HTTPNotFound(text="Channel not found")

    upstream_url = _channel_urls.get(channel_id)
    if not upstream_url:
        raise web.HTTPNotFound(text="Channel not found")

    # 播放量+1
    count = _increment_stat(channel_id)
    logger.info("→ [%s] 播放+1（累计 %d）", channel_id, count)

    try:
        resp = await _stream_upstream_with_retry(upstream_url)
        async with _health_lock:
            h = _health.get(channel_id, {"success": 0, "failure": 0, "last_ok": None})
            h["success"] = h.get("success", 0) + 1
            h["last_ok"] = True
            _health[channel_id] = h

    except asyncio.TimeoutError:
        logger.error("连接 upstream 超时（已重试）: %s", channel_id)
        async with _health_lock:
            h = _health.get(channel_id, {"success": 0, "failure": 0, "last_ok": None})
            h["failure"] = h.get("failure", 0) + 1
            h["last_ok"] = False
            _health[channel_id] = h
        raise web.HTTPBadGateway(text="Upstream connection timeout")

    except Exception as e:
        logger.error("连接 upstream 失败（已重试）: [%s] %s", channel_id, e)
        async with _health_lock:
            h = _health.get(channel_id, {"success": 0, "failure": 0, "last_ok": None})
            h["failure"] = h.get("failure", 0) + 1
            h["last_ok"] = False
            _health[channel_id] = h
        raise web.HTTPBadGateway(text=f"Upstream connection failed: {e}")

    # 记录耗时
    elapsed_ms = (time.monotonic() - start_ms) * 1000
    logger.info("← [%s] %.1fms", channel_id, elapsed_ms)

    content_type = "video/mp2t" if upstream_url.endswith(".ts") else "video/x-flv"
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": content_type,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)

    try:
        async for chunk in resp.content.iter_chunked(8192):
            if not chunk:
                break
            await response.write(chunk)
    except asyncio.TimeoutError:
        logger.error("流传输超时: %s", channel_id)
        raise web.HTTPBadGateway(text="Upstream timeout")
    except (ConnectionResetError, BrokenPipeError):
        logger.warning("客户端断开: %s", channel_id)
    finally:
        await response.write_eof()

    return response


# ---------------------------------------------------------------
# 热重载（SIGHUP）
# ---------------------------------------------------------------

_hup_reload_callbacks: list[callable] = []


def register_hup_reload(callback: callable) -> None:
    """注册 SIGHUP 触发时的回调函数（用于重载频道等）。"""
    _hup_reload_callbacks.append(callback)


async def _setup_sighup_handler(loop) -> None:
    """在主循环中注册 SIGHUP 处理器。"""
    def on_sighup():
        logger.info("收到 SIGHUP，开始热重载...")
        for cb in _hup_reload_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error("热重载回调失败: %s", e)
        logger.info("热重载完成。")

    try:
        loop.add_signal_handler(signal.SIGHUP, on_sighup)
        logger.info("SIGHUP 热重载已注册")
    except (OSError, ValueError):
        logger.warning("当前平台不支持 SIGHUP 热重载")


# ---------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------

async def handle_stats(request: web.Request) -> web.Response:
    """GET /stats — 返回播放量 + 健康指标。"""
    stats = _stats_cache.copy()
    async with _health_lock:
        health = {cid: h.copy() for cid, h in _health.items()}

    total_success = sum(h["success"] for h in health.values())
    total_failure = sum(h["failure"] for h in health.values())
    total = total_success + total_failure
    success_rate = f"{(total_success / total * 100):.1f}%" if total > 0 else "N/A"

    payload = {
        "play_count": stats,
        "health": health,
        "summary": {
            "total_plays": sum(stats.values()),
            "total_success": total_success,
            "total_failure": total_failure,
            "success_rate": success_rate,
        }
    }
    return web.json_response(payload)


def create_app(channel_urls: dict[str, str]) -> web.Application:
    """创建 aiohttp 应用，注册路由。"""
    app = web.Application()
    update_channel_urls(channel_urls)
    _load_stats()

    global _save_task
    loop = asyncio.get_running_loop()
    _save_task = loop.create_task(_periodic_save())

    # SIGHUP 热重载
    loop.create_task(_setup_sighup_handler(loop))

    async def _cleanup(app: web.Application):
        global _save_task, _http_session
        logger.info("清理 proxy 资源...")
        if _save_task:
            _save_task.cancel()
            try:
                await _save_task
            except asyncio.CancelledError:
                pass
        async with _stats_lock:
            if _stats_dirty:
                await _save_stats_async(_stats_cache.copy())
                _stats_dirty = False
        if _http_session and not _http_session.closed:
            await _http_session.close()
        logger.info("清理完成。")

    app.on_cleanup.append(_cleanup)

    app.router.add_get("/mgtv.m3u", handle_mgtv_m3u)
    app.router.add_get("/live/{channel_id}.flv", relay_flv)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/stats", handle_stats)

    return app


# ---------------------------------------------------------------
# 静态路由处理函数
# ---------------------------------------------------------------
from pathlib import Path


async def handle_mgtv_m3u(request: web.Request) -> web.Response:
    """提供 m3u 订阅文件。"""
    m3u_path = Path(__file__).parent.parent.parent / "mgtv.m3u"
    try:
        content = m3u_path.read_text(encoding="utf-8")
        return web.Response(text=content, content_type="application/vnd.apple.mpegurl")
    except FileNotFoundError:
        raise web.HTTPNotFound(text="mgtv.m3u not found")


async def handle_health(request: web.Request) -> web.Response:
    """健康检查。"""
    async with _health_lock:
        health = {cid: h.copy() for cid, h in _health.items()}
    total_ok = sum(1 for h in health.values() if h.get("last_ok"))
    return web.json_response({
        "status": "ok" if total_ok > 0 else "degraded",
        "channels": len(_channel_urls),
        "healthy_channels": total_ok,
        "channel_health": health,
    })
