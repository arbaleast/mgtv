import pytest
from src.generator.m3u import M3uGenerator, generate_live_url, generate_mgtv_m3u
from src.api.fetcher import ChannelResult


def test_generate_live_url_with_tunnel():
    url = generate_live_url("280", "abc.trycloudflare.com")
    assert url == "https://abc.trycloudflare.com/live/280.flv"


def test_generate_live_url_no_tunnel():
    url = generate_live_url("280", "")
    assert url == "http://localhost:8080/live/280.flv"


def test_mgtv_m3u_format():
    results = [
        ChannelResult(channel_id="280", name="湖南经视", logo="", url="http://x", ok=True),
        ChannelResult(channel_id="346", name="湖南都市", logo="", url="http://y", ok=True),
    ]
    m3u = generate_mgtv_m3u(results, "abc.trycloudflare.com")
    assert m3u.startswith("#EXTM3U\n")
    assert 'tvg-id="280"' in m3u
    assert 'tvg-name="湖南经视"' in m3u


def test_mgtv_m3u_skips_failed():
    results = [
        ChannelResult(channel_id="280", name="湖南经视", url="", ok=False, error="offline"),
    ]
    m3u = generate_mgtv_m3u(results, "abc.trycloudflare.com")
    assert "湖南经视" not in m3u  # failed results skipped


def test_m3u_generator_class():
    gen = M3uGenerator()
    results = [ChannelResult(channel_id="280", name="湖南经视", url="http://x", ok=True)]
    content = gen.generate(results, "abc.trycloudflare.com")
    assert 'tvg-name="湖南经视"' in content
