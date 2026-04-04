# 🍋 芒果 TV 直播源

湖南地方频道 m3u 订阅文件。

## 订阅地址

```
https://mirror.ghproxy.com/https://raw.githubusercontent.com/arbaleast/mgtv/main/mgtv.m3u
```

镜像加速，适合国内网络。

## 技术方案

| 技术 | 说明 |
|------|------|
| **asyncio + aiohttp** | 并发请求，13 频道 ~500ms |
| **GitHub Actions** | 每日 UTC 0:00（北京时间 08:00）自动刷新 |
| **M3U + FLV** | HTTP-FLV 流，兼容大多数 IPTV 软件 |

## 项目结构

```
src/
├── fetcher.py          # 并发获取直播 URL
├── m3u8_generator.py  # 生成 m3u 播放列表
├── channels.json       # 频道映射表
└── config.py          # 全局配置
```

## 本地使用

```bash
pip install -r requirements.txt
python -m src.fetcher
```

## 参考

- [HLS.js](https://github.com/video-dev/hls.js)
- [IETF HTTP Live Streaming](https://datatracker.ietf.org/doc/html/draft-pantos-hls-rfc8216bis)
- [Nuxt SSR](https://nuxt.com/docs/getting-started/introduction)
- [aiohttp](https://docs.aiohttp.org/)
