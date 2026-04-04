# MGTV 直播源项目改进设计

> 日期：2026-04-04
> 状态：设计中

## 背景

当前项目 `arbaleast/mgtv` 存在直播源失效问题，根源是旧 API `mpp.liveapi.mgtv.com` 返回的 CDN URL 含过期时间戳（IP 绑定）。通过 JS 逆向分析芒果 TV 直播页，发现新 API `pwlp.bz.mgtv.com/v1/live/source` 可获取稳定的直播流地址，但需签名鉴权。

## 改进目标

1. 接入新 API，解决直播源频繁失效
2. 提升脚本性能和代码质量
3. 规范化项目结构、命名、注释
4. 重写 README，强化法律意识

## 项目结构

```
mgtv/
├── src/
│   ├── __init__.py
│   ├── channels.json          # 频道映射表（channel_id → activityId/cameraId）
│   ├── config.py              # 环境变量配置（密钥从 env 读取，不硬编码）
│   ├── fetcher.py             # 并发获取直播源（新API + fallback）
│   └── m3u8_generator.py      # 生成聚合 m3u 文件
├── .github/workflows/
│   └── update-channels.yml    # GitHub Actions 定时任务
├── requirements.txt
├── pyproject.toml
├── .gitignore
└── README.md
```

## 命名规范

| 类型 | 规则 | 示例 |
|------|------|------|
| Python 模块 | snake_case | `fetcher.py` |
| 配置文件 | snake_case | `config.py` |
| JSON 数据 | snake_case | `channels.json` |
| GitHub Actions | kebab-case | `update-channels.yml` |
| 环境变量 | UPPER_SNAKE | `MGTV_CLIENT_SECRET` |

## 核心算法设计

### 旧设计性能问题

```
generate_live_stream_urls()  ──→  for loop 逐个 subprocess 调用
                                    串行等待 → 15 频道 ≈ 7.5s+
                                  → 逐个读写文件
```

### 优化后

```python
async def fetch_all_channels(channels: list[dict]) -> list[dict]:
    """并发获取所有频道直播源。
    
    所有频道同时请求，总耗时 ≈ 最慢那一个，而非总和。
    """
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_single(session, ch) for ch in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict) and r.get("url")]
```

### 性能对比

| # | 旧方案 | 新方案 |
|---|--------|--------|
| 请求方式 | 串行 for 循环 | asyncio + aiohttp 并发 |
| 总耗时 | O(n) × 500ms | O(1) ≈ 500ms |
| 文件 I/O | 逐个写 | aiofiles 并发写 |
| 进程开销 | subprocess 创建新进程 | 直接函数调用 |

## API 设计

### 新 API（主方案）

```
GET https://pwlp.bz.mgtv.com/v1/live/source
参数: activityId, cameraId, platform=4, appVersion, clientKey, auth_mode, init_definition, _t, sign
签名: MD5(secret + sortedParams + secret)
密钥: 从 MGTV_CLIENT_SECRET 环境变量读取
```

### 旧 API（已废弃，不做 fallback）

旧 API `mpp.liveapi.mgtv.com` 时效短且不稳定，本次直接移除。

## 法律与合规

- 不在代码/文档中暴露 API 密钥
- README 明确"仅供个人学习，侵权即删"
- 不声称官方授权
- 频道映射表 channel_id 来自公开渠道整理

## 实现计划

- [ ] 编写 `config.py`（环境变量读取）
- [ ] 建立 `channels.json`（频道映射表）
- [ ] 实现 `fetcher.py`（并发请求逻辑）
- [ ] 重写 `m3u8_generator.py`
- [ ] 更新 GitHub Actions workflow
- [ ] 重写 README
- [ ] 本地测试验证
