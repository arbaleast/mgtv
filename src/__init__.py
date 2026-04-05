"""mgtv-streams - 芒果 TV 直播流代理。"""
from .api import MgtvClient, ChannelResult
from .generator import M3uGenerator

__all__ = ["MgtvClient", "ChannelResult", "M3uGenerator"]
