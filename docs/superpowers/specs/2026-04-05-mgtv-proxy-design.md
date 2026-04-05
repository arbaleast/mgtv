# mgtv 重构设计方案

## 背景与问题

### 现状
- mgtv 项目从芒果 TV 旧 API（`mpp.liveapi.mgtv.com`）获取直播流地址
- API 返回的 CDN URL 内嵌了请求服务器的 IP（base64 编码），用于 IP 鉴权
- GitHub Actions 调度时请求来自 Actions 服务器 IP，用户播放时 IP 不匹配 → 403 Forbidden

### 核心矛盾
- 芒果 TV API 限制 IP，必须在中国大陆 IP 下请求才能获取可用 URL
- 原始项目运行在 GitHub Actions（境外 IP），URL 对用户无效

### 其他问题
- `m3u8/hn##.m3u8` 文件格式错误（HLS 包装了 FLV 地址），完全无法播放
- 无测试，无类型提示，docstring 放置错误

---

## 设计目标

1. **可用性**：用户播放地址可正常工作
2. **可维护性**：代码质量达标（类型提示、测试、清晰结构）
3. **可扩展性**：支持多源 API 切换

---

## 整体架构

```
芒果 TV API
  (国内 IP 可达，返回真实 FLV URL)
        │
        ▼
┌─────────────────────┐
│  本机（国内固定 IP）   │
│  ┌───────────────┐  │
│  │  Fetcher      │  │  定时从芒果 API 获取有效 stream URL
│  └───────┬───────┘  │
│          │          │
│  ┌───────▼───────┐  │
│  │  Proxy Server │  │  HTTP FLV 流媒体代理
│  │  :8080        │  │  接收播放器请求，relay FLV 流
│  └───────┬───────┘  │
│          │          │
│  ┌───────▼───────┐  │
│  │ cloudflared   │  │  Cloudflare Tunnel 暴露本机端口
│  │ tunnel        │  │  生成可访问的公网地址
│  └───────────────┘  │
└─────────────────────┘
        │
        ▼
  用户播放器
  (PotPlayer / VLC / IINA)
```

---

## 核心组件

### 1. Fetcher（`src/fetcher.py`）
- 从芒果 TV API 获取真实 FLV 流地址
- 定时刷新（15 分钟间隔），避免 URL 时效过期
- 支持旧 API（已验证可用）和新 API（预留）
- 输出：`{channel_id: str, name: str, url: str, logo: str}`

### 2. Proxy Server（`src/proxy.py`）
- HTTP FLV 流媒体服务器，端口 `8080`
- 路由：`GET /live/{channel_id}` → 返回 FLV 流
- 多用户共享：多个播放器请求同一频道时，只向芒果 TV 建立一条 upstream 连接
- 错误处理：upstream 断开时返回适当 HTTP 状态码

### 3. M3U Generator（`src/m3u_generator.py`）
- 生成订阅文件 `mgtv.m3u`
- URL 指向 tunnel 地址：`https://{tunnel_domain}/live/{channel_id}.flv`
- 移除错误的 `m3u8/` 目录

### 4. Server（`src/server.py`）
- 启动入口
- 顺序：启动 proxy → 立即执行一次 fetch → 启动定时刷新任务
- 优雅退出：捕获信号，正确关闭连接和定时器

### 5. Tunnel Manager（`src/tunnel.py`）
- 封装 cloudflared 进程管理
- 启动 tunnel，解析输出获取公网地址
- 定期健康检查，tunnel 断开时自动重连
- 地址写入共享配置，供 m3u_generator 使用

### 6. Config（`src/config.py`）
- `SERVER_HOST`: 本机监听地址（默认 `0.0.0.0`）
- `SERVER_PORT`: 本机监听端口（默认 `8080`）
- `FETCH_INTERVAL_MINUTES`: 刷新间隔（默认 `15`）
- `TUNNEL_DOMAIN`: cloudflared tunnel 公网地址（运行时写入）

---

## 技术选型

### HTTP FLV 而非 HLS
| 维度 | HTTP FLV | HLS |
|------|----------|-----|
| 协议 | FLV over HTTP | m3u8 + TS 分片 |
| 延迟 | 1~3 秒 | 5~10 秒 |
| 实现复杂度 | 低，直接 relay | 高，需转码/分片 |
| 播放器支持 | PotPlayer/VLC/IINA 全支持 | 部分播放器不支持 FLV |

芒果 TV 本身就是 FLV 流，HTTP FLV 中转最简单高效。

### 依赖
```
aiohttp>=3.9.0     # 异步 HTTP 请求
httpx>=0.25.0      # 同步 HTTP（proxy 用）
pydantic>=2.0      # 类型验证和配置模型
pyyaml>=6.0        # 配置文件
```

---

## 文件结构

```
mgtv/
├── src/
│   ├── __init__.py
│   ├── fetcher.py          # 芒果 API 请求、URL 刷新
│   ├── proxy.py            # HTTP FLV 代理服务器
│   ├── m3u_generator.py    # m3u 文件生成
│   ├── tunnel.py           # cloudflared 进程管理
│   ├── config.py           # 配置模型
│   └── server.py           # 启动入口
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-05-mgtv-proxy-design.md
├── run.sh                  # 一键启动脚本
├── requirements.txt
├── pyproject.toml
└── tests/
    ├── test_fetcher.py
    ├── test_proxy.py
    └── test_m3u_generator.py
```

---

## 启动流程

```
1. 安装依赖
   pip install -r requirements.txt

2. 启动 cloudflared tunnel（后台）
   cloudflared tunnel --url http://localhost:8080

3. 启动 mgtv server
   python -m src.server

   或使用 run.sh（自动启动 tunnel + server）
   ./run.sh
```

---

## 播放地址格式

```
主订阅文件：mgtv.m3u
https://{tunnel-id}.trycloudflare.com/live/280.flv   # 湖南经视
https://{tunnel-id}.trycloudflare.com/live/346.flv   # 湖南都市
...
```

---

## 错误处理

| 场景 | 处理 |
|------|------|
| 芒果 API 请求失败 | 重试 3 次，间隔 5s；仍失败则保留旧 URL |
| tunnel 断开 | 自动重连，刷新公网地址，更新 m3u |
| upstream FLV 流断开 | proxy 返回 502，播放器自动重试 |
| 频道下线 | 从 m3u 中移除，不再生成分发地址 |

---

## 待探索

- [ ] 验证 Cloudflare Tunnel 在国内网络对播放器的可达性
- [ ] 测试实际 FLV relay 的稳定性和延迟
- [ ] cloudflared 安装方式（apt / binary / pip）
