# tests/test_proxy_layer.py
import pytest
from src.proxy.relay import update_channel_urls
from src.proxy.routes import create_app
import src.proxy.relay as relay_module


def test_update_channel_urls():
    update_channel_urls({"280": "http://x", "346": "http://y"})
    assert relay_module._channel_urls == {"280": "http://x", "346": "http://y"}


def test_create_app_has_routes():
    app = create_app({"280": "http://x"})
    routes = [r.resource.canonical for r in app.router.routes()]
    paths = [r for r in routes]
    assert any("/mgtv.m3u" in str(r) for r in paths)
    assert any("/health" in str(r) for r in paths)
    assert any("/live/{channel_id}.flv" in str(r) for r in paths)
