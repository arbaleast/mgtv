"""Tests for src.fetcher."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.fetcher import _parse_response, fetch_single


CHANNEL_MOCK = {"channel_id": "280", "name": "湖南经视", "logo": "https://example.com/logo.png"}


def test_parse_response_success():
    raw = {"errno": "0", "msg": "成功", "data": {"url": "http://example.com/test.flv", "npuk": "test"}}
    result = _parse_response(raw, CHANNEL_MOCK)
    assert result.ok is True
    assert result.url == "http://example.com/test.flv"
    assert result.channel_id == "280"
    assert result.name == "湖南经视"


def test_parse_response_fail_errno():
    raw = {"errno": "2040114", "msg": "该机位已下线"}
    result = _parse_response(raw, CHANNEL_MOCK)
    assert result.ok is False
    assert "下线" in result.error


def test_parse_response_no_url():
    raw = {"errno": "0", "data": {}}
    result = _parse_response(raw, CHANNEL_MOCK)
    assert result.ok is False
    assert "无 url" in result.error


def test_parse_response_unknown_errno():
    raw = {"errno": "999999", "msg": "服务器内部错误"}
    result = _parse_response(raw, CHANNEL_MOCK)
    assert result.ok is False
    assert result.error == "服务器内部错误"


@pytest.mark.asyncio
async def test_fetch_single_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value='{"errno":"0","data":{"url":"http://test.flv"}}')
    # async with session.get() 需要返回 __aenter__ 的结果
    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    result = await fetch_single(mock_session, CHANNEL_MOCK)
    assert result.ok is True
    assert "test.flv" in result.url
