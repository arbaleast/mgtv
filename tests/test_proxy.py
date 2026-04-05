"""Tests for src.proxy."""
import pytest
from src.proxy import make_channel_id_pattern


def test_channel_id_pattern_valid():
    # 匹配完整路径 /live/{channel_id}.flv
    pattern = make_channel_id_pattern(["280", "346"])
    assert pattern.match("/live/280.flv") is not None
    assert pattern.match("/live/346.flv") is not None


def test_channel_id_pattern_invalid():
    pattern = make_channel_id_pattern(["280"])
    assert pattern.match("/live/999.flv") is None
    assert pattern.match("/live/abc.flv") is None


def test_channel_id_pattern_no_match():
    # 不匹配无路径的 channel id
    pattern = make_channel_id_pattern(["280"])
    assert pattern.match("280") is None
