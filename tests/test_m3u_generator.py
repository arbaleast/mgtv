"""Tests for src.m3u_generator."""
import pytest
from src.generator.m3u import generate_live_url, generate_mgtv_m3u
from src.api.fetcher import ChannelResult


def test_generate_live_url_with_tunnel():
    url = generate_live_url("280", tunnel_domain="abc.trycloudflare.com")
    assert url == "https://abc.trycloudflare.com/live/280.flv"


def test_generate_live_url_no_tunnel():
    url = generate_live_url("280", tunnel_domain="")
    assert url == "http://localhost:8080/live/280.flv"


def test_mgtv_m3u_format():
    results = [
        ChannelResult(channel_id="280", name="湖南经视", logo="https://x.com/hnjs.png", url="http://test.flv", ok=True),
    ]
    content = generate_mgtv_m3u(results, tunnel_domain="abc.trycloudflare.com")
    assert "#EXTM3U" in content
    assert "湖南经视" in content
    assert "abc.trycloudflare.com/live/280.flv" in content
    assert "#EXT-X" not in content  # 不应该有 HLS 内容


def test_mgtv_m3u_skips_failed():
    results = [
        ChannelResult(channel_id="280", name="湖南经视", url="", ok=False, error="offline"),
        ChannelResult(channel_id="346", name="湖南都市", url="http://test.flv", ok=True),
    ]
    content = generate_mgtv_m3u(results, tunnel_domain="abc.trycloudflare.com")
    assert "湖南经视" not in content  # failed channel skipped
    assert "湖南都市" in content
