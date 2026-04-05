#!/bin/bash
# 芒果 TV 直播源 proxy 启动脚本
# 用法: ./run.sh
#
# 启动流程:
#   1. 安装依赖
#   2. 启动 proxy server + cloudflared tunnel
#   3. 定时刷新频道 URL
#
# 前置要求: 安装 cloudflared
#   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
#     -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

set -e
cd "$(dirname "$0")"

echo "[*] 安装依赖..."
pip install -q -r requirements.txt 2>/dev/null

echo "[*] 启动 mgtv server..."
python -m src.server
