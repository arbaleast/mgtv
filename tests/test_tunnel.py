"""Tests for src.tunnel."""
import pytest
from src.tunnel import parse_tunnel_url, is_cloudflared_installed


def test_parse_tunnel_url():
    line = '2026-04-05T12:00:00Z INF Requesting new tunnel on trycloudflare.com address: abc123.trycloudflare.com'
    url = parse_tunnel_url(line)
    assert url == "abc123.trycloudflare.com"


def test_parse_tunnel_url_no_match():
    url = parse_tunnel_url('some unrelated log line')
    assert url is None


def test_is_cloudflared_installed():
    # 返回 bool，不抛异常
    result = is_cloudflared_installed()
    assert isinstance(result, bool)
