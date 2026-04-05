#!/usr/bin/env python3
"""自动为 channels.json 填充 group 字段。

支持两种模式：
1. 关键词匹配（自动）：根据频道名称关键词推断分组
2. 显式映射（手动）：通过 GROUP_MAP 覆盖特定频道的分组

用法：
    python scripts/fetch_channels.py              # 预览改动
    python scripts/fetch_channels.py --apply      # 写入 channels.json
    python scripts/fetch_channels.py --apply -f   # 强制写入（跳过确认）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------
# 分组规则：按优先级匹配，匹配到则返回对应 group
# key 为正则或普通字符串，value 为 group 名称
# ---------------------------------------------------------------
GROUP_RULES: list[tuple[re.Pattern | str, str]] = [
    # CCTV
    (re.compile(r"^cctv\d+", re.IGNORECASE), "CCTV"),
    # 湖南（默认）
    (re.compile(r"^(湖南|金鹰|快乐|长沙|茶频道|先锋)", re.IGNORECASE), "湖南"),
    # 卫视频道
    (re.compile(r"(东方|浙江|江苏|北京|深圳|广东|四川|湖北|安徽|山东)", re.IGNORECASE), "卫视频道"),
    # 港澳台
    (re.compile(r"(凤凰|RTHK|TVB|中天|华视|东森|非凡)", re.IGNORECASE), "港澳台"),
    # 电影
    (re.compile(r"电影|Cine", re.IGNORECASE), "电影"),
    # 体育
    (re.compile(r"(体育|高尔夫|网球|足球|CCTV-5)", re.IGNORECASE), "体育"),
    # 新闻
    (re.compile(r"(新闻|CCTV-13|凤凰资讯)", re.IGNORECASE), "新闻"),
    # 财经
    (re.compile(r"(财经|CCTV-2)", re.IGNORECASE), "财经"),
    # 纪录
    (re.compile(r"(纪录|Discovery|BBC)", re.IGNORECASE), "纪录"),
    # 少儿
    (re.compile(r"(少儿|动漫|CCTV-14|金鹰卡通)", re.IGNORECASE), "少儿"),
    # 音乐
    (re.compile(r"(音乐|MTV|VMV)", re.IGNORECASE), "音乐"),
]

# 显式分组映射（覆盖规则匹配结果，优先级最高）
GROUP_MAP: dict[str, str] = {
    # "channel_id": "GroupName",
    # 示例：
    # "cctv1": "CCTV",
    # "hunan": "湖南",
}


def detect_group(channel: dict) -> str:
    """根据频道信息推断分组。"""
    # 1. 优先检查显式映射
    cid = channel.get("channel_id", "")
    if cid in GROUP_MAP:
        return GROUP_MAP[cid]

    name = channel.get("name", "")

    # 2. 检查 group 字段是否已存在且非空
    existing = channel.get("group", "")
    if existing:
        return existing

    # 3. 按规则匹配
    for pattern, group in GROUP_RULES:
        if hasattr(pattern, "search"):  # re.Pattern
            if pattern.search(name) or pattern.search(cid):
                return group
        else:  # plain string
            if pattern.lower() in name.lower() or pattern.lower() in cid.lower():
                return group

    return "其他"


def process_channels(channels: list[dict]) -> tuple[list[dict], list[dict]]:
    """为所有频道填充 group 字段，返回 (updated, unchanged)。"""
    updated = []
    unchanged = []

    for ch in channels:
        old_group = ch.get("group", "")
        new_group = detect_group(ch)
        ch["group"] = new_group

        if old_group != new_group:
            updated.append((ch, old_group, new_group))
        else:
            unchanged.append(ch)

    return updated, unchanged


def print_diff(updated: list[tuple[dict, str, str]]):
    """打印变更明细。"""
    if not updated:
        print("所有频道已有 group 字段，无需更新。")
        return

    print(f"将更新 {len(updated)} 个频道的 group：\n")
    print(f"{'Channel ID':<12} {'Name':<20} {'Old':<12} {'New'}")
    print("-" * 65)
    for ch, old, new in updated:
        print(f"{ch['channel_id']:<12} {ch['name']:<20} {old or '(none)':<12} {new}")


def main():
    parser = argparse.ArgumentParser(description="为 channels.json 填充 group 字段")
    parser.add_argument("--apply", action="store_true", help="写入 channels.json（默认仅预览）")
    parser.add_argument("-f", "--force", action="store_true", help="强制写入，跳过确认")
    parser.add_argument(
        "--file", "-i", type=Path, default=None,
        help="指定 channels.json 路径（默认从 src/config.py 推断）"
    )
    args = parser.parse_args()

    # 确定 channels.json 路径
    if args.file:
        channels_file = args.file
    else:
        # 从项目根目录推断
        project_root = Path(__file__).parent.parent
        channels_file = project_root / "src" / "channels.json"

    if not channels_file.exists():
        print(f"[ERROR] 文件不存在: {channels_file}", file=sys.stderr)
        sys.exit(1)

    with open(channels_file, encoding="utf-8") as f:
        data = json.load(f)

    channels = data.get("channels", [])
    if not channels:
        print("[ERROR] channels.json 中没有 channels 列表", file=sys.stderr)
        sys.exit(1)

    updated, unchanged = process_channels(channels)
    print_diff(updated)
    print(f"\n未变更: {len(unchanged)} 个")

    if not args.apply:
        print("\n（预览模式，使用 --apply 写入变更）")
        return

    if not args.force:
        confirm = input("\n确认写入？[y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("已取消。")
            return

    # 写回文件，保持原有格式（pretty print）
    with open(channels_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n已写入: {channels_file}")


if __name__ == "__main__":
    main()
