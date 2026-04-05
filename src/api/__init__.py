"""从芒果 TV API 获取直播流地址。

导出:
- MgtvClient: 芒果 TV API 客户端
- ChannelResult: 单个频道的抓取结果
"""
from .client import MgtvClient
from .fetcher import ChannelResult

__all__ = ["MgtvClient", "ChannelResult"]
