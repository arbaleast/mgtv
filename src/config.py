"""全局配置 — Pydantic Settings."""
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """应用全局配置。"""

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8080

    # Fetch
    fetch_interval_minutes: int = 15
    request_timeout: int = 10

    # EPG（未来扩展）
    epg_enabled: bool = False
    epg_cache_hours: int = 24

    # Tunnel
    tunnel_domain: str = ""

    @property
    def channels_file(self) -> Path:
        return Path(__file__).parent / "channels.json"


settings = Settings()
