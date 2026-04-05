# 芒果 TV 直播源

湖南地方频道 + CCTV + 卫视频道 m3u 订阅文件，支持本地 proxy 服务器（HTTP-FLV 中转 + Cloudflare Tunnel）。

## 订阅地址

| 地址 | 适用场景 |
|------|---------|
| `https://ghproxy.com/https://raw.githubusercontent.com/arbaleast/mgtv/main/mgtv.m3u` | 国内加速 |
| `https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/mgtv.m3u` | 全球加速（jsDelivr CDN）|

## 频道列表

### 湖南（13 个频道）
湖南经视、湖南都市、湖南电视剧、湖南公共、湖南国际、湖南娱乐、快乐购、金鹰纪实、金鹰卡通、快乐垂钓、长沙新闻、长沙政法、长沙女性

### CCTV（4 个频道）
CCTV-1 综合、CCTV-2 财经、CCTV-5 体育、CCTV-13 新闻

### 更多频道
东方卫视、浙江卫视、江苏卫视、北京卫视、凤凰中文、凤凰资讯 等（持续添加中）

## 功能特性

### 播放量统计
- 内存计数 + 异步批量持久化（每 30s 刷盘）
- `GET /stats` 接口查询所有频道播放量 + 健康指标
- 服务重启后统计不丢失

### 健康指标
- per-channel `success / failure / last_ok`
- 汇总 `total_success / total_failure / success_rate`
- `GET /health` 实时查看

### 上游重试
- 超时、5xx 错误自动重试最多 3 次
- 指数退避：0.5s → 1s → 2s

### 速率限制
- 每 IP 每频道最高 10 req/s
- 超限返回 `429 TooManyRequests`

### 热重载
- 收到 `SIGHUP` 信号自动重新加载 `channels.json`
- 无需重启服务即可更新频道配置

### 其他
- 连接池复用（全局 TCPConnector，按 host 限制并发）
- 启动时检查 static 频道 URL 可用性
- 单频道 `.m3u8` 文件（`m3u8/` 目录）
- 请求耗时日志（毫秒级）

## 技术方案

### 流媒体协议

| 协议 | 格式 | 说明 |
|------|------|------|
| **HTTP-FLV** | FLV over HTTP | 低延迟，直播场景广泛使用 |
| **HLS** | m3u8 + TS segment | Apple 主推，兼容性极强，延迟较高 |

本项目生成的 m3u 文件为 HTTP-FLV 流，可被绝大多数 IPTV 软件（PotPlayer、VLC、IINA）直接播放。

### 架构设计

```
用户请求
    │
    ▼
GitHub Actions (每日 08:00 UTC)
    │
    ├── asyncio 并发请求所有频道
    │
    ├── 解析 API 响应，提取 url 字段
    │
    └── 生成 m3u 播放列表
            ├── mgtv.m3u        ← 聚合文件（所有频道）
            └── m3u8/*.m3u8   ← 单频道独立文件

本地 Proxy 模式（可选）
    │
    ├── cloudflared tunnel → 公网访问
    ├── /live/{id}.flv     → relay 上游流
    ├── /stats             → 播放量+健康指标
    └── /health            → 服务健康检查
```

## 项目结构

```
mgtv/
├── src/
│   ├── api/
│   │   ├── client.py      # 芒果 TV API 客户端
│   │   ├── epg.py         # EPG 数据（未来扩展）
│   │   └── fetcher.py     # asyncio 并发抓取，ChannelResult
│   ├── generator/
│   │   ├── epg.py         # EPG 生成（未来扩展）
│   │   └── m3u.py          # m3u 播放列表生成
│   ├── proxy/
│   │   ├── relay.py       # HTTP-FLV 中转核心
│   │   └── routes.py      # 路由注册
│   ├── tunnel.py          # cloudflared tunnel 管理
│   ├── server.py          # proxy 服务入口
│   ├── config.py          # Pydantic 全局配置
│   └── channels.json      # 频道定义（ID/名称/Logo/分组/URL）
├── scripts/
│   └── fetch_channels.py  # 自动填充 group 字段脚本
├── m3u8/                  # 单频道 m3u8 文件（生成）
├── tests/                 # pytest 单元测试
├── requirements.txt
└── pyproject.toml
```

## 本地使用

### 快速抓取（仅生成 m3u）
```bash
pip install -r requirements.txt
python -m src.fetcher
```

### 启动 Proxy 服务器
```bash
# 需要安装 cloudflared
# https://github.com/cloudflare/cloudflared/releases
python -m src.server
```

### 自动填充频道分组
```bash
python scripts/fetch_channels.py              # 预览
python scripts/fetch_channels.py --apply      # 写入（需确认）
python scripts/fetch_channels.py --apply -f   # 强制写入
```

## API 接口（Proxy 模式）

| 接口 | 说明 |
|------|------|
| `GET /mgtv.m3u` | m3u 订阅文件 |
| `GET /live/{channel_id}.flv` | 播放频道（relay 上游 FLV/TS 流） |
| `GET /stats` | 播放量统计 + 健康指标 |
| `GET /health` | 服务健康检查 |
| `GET /m3u8/{channel_id}.m3u8` | 单频道 m3u8 文件 |

## GitHub Actions 自动更新

workflow 文件：`.github/workflows/update-channels.yml`

每日 `08:00 UTC` 自动抓取频道 URL 并更新 `mgtv.m3u`，Commit 后触发 GitHub Pages/CDN 更新。

## 参考资料

| 主题 | 文档 |
|------|------|
| HLS 协议标准 | [IETF draft-pantos-hls-rfc8216bis](https://datatracker.ietf.org/doc/html/draft-pantos-hls-rfc8216bis) |
| asyncio 异步编程 | [docs.python.org/3/library/asyncio](https://docs.python.org/3/library/asyncio.html) |
| aiohttp HTTP 客户端 | [docs.aiohttp.org](https://docs.aiohttp.org) |
| cloudflared tunnel | [developers.cloudflare.com/cloudflare-one/connections/connect-networks/install-and-setup/tunnel-guide](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/install-and-setup/tunnel-guide) |
