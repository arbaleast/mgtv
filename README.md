# 芒果 TV 直播源

湖南地方频道 m3u 订阅文件。

## 订阅地址

| 地址 | 适用场景 |
|------|---------|
| `https://ghproxy.com/https://raw.githubusercontent.com/arbaleast/mgtv/main/mgtv.m3u` | 国内加速 |
| `https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/mgtv.m3u` | 全球加速（jsDelivr CDN）|

## 技术方案

### 流媒体协议

| 协议 | 格式 | 说明 |
|------|------|------|
| **HTTP-FLV** | FLV over HTTP | 低延迟，直播场景广泛使用 |
| **HLS** | m3u8 + TS segment | Apple 主推，兼容性极强，延迟较高 |
| **DASH** | MPD + M4S | ISO 标准，HLS 的替代方案 |

本项目生成的 m3u 文件为 HTTP-FLV 流，可被绝大多数 IPTV 软件（PotPlayer、VLC、IINA）直接播放。

### 架构设计

```
用户请求
    │
    ▼
GitHub Actions (每日 08:00 UTC)
    │
    ├── asyncio 并发请求 13 个频道
    │       每个请求 ~500ms，并发总耗时 ≈ 500ms
    │
    ├── 解析 API 响应，提取 url 字段
    │
    └── 生成 m3u 播放列表
            ├── mgtv.m3u        ← 聚合文件（所有频道）
            └── m3u8/hn##.m3u8 ← 单频道独立文件
```

### 核心实现

**并发请求（asyncio）：**
```python
async def fetch_all(channels: list[dict]) -> list[dict]:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_single(session, ch) for ch in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]
```

**m3u 生成：**
```python
def generate_m3u_header(channel: dict) -> str:
    return (
        f'#EXTINF:-1 tvg-id="{channel["channel_id"]}" '
        f'tvg-name="{channel["name"]}" '
        f'tvg-logo="{channel["logo"]}" '
        f'group-title="湖南",{channel["name"]} \n'
    )
```

### 性能对比

| 方案 | 13 频道耗时 | 说明 |
|------|------------|------|
| 串行 for 循环 | ~6.5s | 每个 500ms，顺序累加 |
| **asyncio 并发（当前）** | **~500ms** | 并发请求，最慢那个决定总时间 |
| 优化潜力 | — | aiofiles 并发写文件可进一步提升 |

## 项目结构

```
mgtv/
├── src/
│   ├── fetcher.py           # asyncio 并发请求，解析 API 响应
│   ├── m3u8_generator.py   # 生成 M3U 播放列表
│   ├── channels.json        # 频道 ID → 名称/Logo 映射表
│   └── config.py           # API 端点、超时等配置
├── .github/workflows/
│   └── update-channels.yml # 每日自动刷新
├── requirements.txt
└── pyproject.toml
```

## 本地使用

```bash
pip install -r requirements.txt
python -m src.fetcher
```

## 参考资料

| 主题 | 文档 |
|------|------|
| HLS 协议标准 | [IETF draft-pantos-hls-rfc8216bis](https://datatracker.ietf.org/doc/html/draft-pantos-hls-rfc8216bis) |
| HLS.js 播放器 | [github.com/video-dev/hls.js](https://github.com/video-dev/hls.js) |
| asyncio 异步编程 | [docs.python.org/3/library/asyncio](https://docs.python.org/3/library/asyncio.html) |
| aiohttp HTTP 客户端 | [docs.aiohttp.org](https://docs.aiohttp.org) |
| Nuxt SSR 机制 | [nuxt.com/docs/getting-started/introduction](https://nuxt.com/docs/getting-started/introduction) |
