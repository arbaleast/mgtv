"""全局配置 — Pydantic Settings."""
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """应用全局配置。"""

    server_host: str = "0.0.0.0"
    server_port: int = 8080
    fetch_interval_minutes: int = 15
    tunnel_domain: str = ""  # 运行时由 tunnel.py 写入

    @property
    def channels_file(self) -> Path:
        return Path(__file__).parent / "channels.json"


settings = Settings()
