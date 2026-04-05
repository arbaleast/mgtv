"""Tests for src.config — Pydantic Settings."""
import pytest
from pydantic import ValidationError
from src.config import Settings


def test_default_values():
    s = Settings()
    assert s.server_host == "0.0.0.0"
    assert s.server_port == 8080
    assert s.fetch_interval_minutes == 15


def test_env_override():
    s = Settings(server_port=9000)
    assert s.server_port == 9000


def test_channels_file_default():
    s = Settings()
    assert s.channels_file.name == "channels.json"
    assert s.channels_file.parent.name == "src"
