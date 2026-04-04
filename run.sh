#!/bin/bash
# 本地运行：自动刷新芒果 TV 直播源
# 用法: ./run.sh

set -e

REPO_DIR="${HOME}/mgtv"

# 1. 克隆或更新
if [ -d "$REPO_DIR/.git" ]; then
    echo "[*] 更新已有仓库..."
    cd "$REPO_DIR" && git pull origin main
else
    echo "[*] 克隆仓库..."
    git clone https://github.com/arbaleast/mgtv.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 2. 安装依赖
echo "[*] 安装依赖..."
pip install -q -r requirements.txt

# 3. 拉取最新直播 URL
echo "[*] 获取直播源..."
python -m src.fetcher

# 4. 提交并推送
cd "$REPO_DIR"
if git diff --quiet mgtv.m3u m3u8/; then
    echo "[*] URL 未变化，无需提交。"
else
    echo "[*] 提交并推送..."
    git config user.email "3309839520@qq.com"
    git config user.name "arbaleast"
    git add mgtv.m3u m3u8/
    git commit -m "update: refresh live URLs $(date '+%Y-%m-%d %H:%M')"
    git push origin main
    echo "[+] 完成！"
fi
