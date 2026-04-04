"""全局配置。

所有敏感信息从环境变量读取，不硬编码在代码中。
"""
import os

# 旧 API 端点（主方案）
OLD_API_BASE = "http://mpp.liveapi.mgtv.com/v1/epg/turnplay/getLivePlayUrlMPP"

# 新 API 端点（备用，待激活）
NEW_API_BASE = "https://pwlp.bz.mgtv.com/v1/live/source"
NEW_API_SECRET = os.getenv("MGTV_CLIENT_SECRET", "")

# 并发请求超时（秒）
REQUEST_TIMEOUT = 10

# User-Agent
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.mgtv.com/",
}
