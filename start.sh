#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -f "$(dirname "$0")/.api_key" ]; then
    export AGNES_API_KEY="$(cat "$(dirname "$0")/.api_key")"
else
    echo "错误: .api_key 文件不存在，请在项目根目录创建 .api_key 并写入 Agnes API Key"
    exit 1
fi
VENV_PYTHON=".venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "虚拟环境不存在，请先运行: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi
if [ $# -eq 0 ]; then
    echo "可用的创意配置:"
    echo ""
    $VENV_PYTHON run_creative.py --list
    echo ""
    echo "用法: ./start.sh <创意名称>"
    echo "示例: ./start.sh singing_dancing"
    exit 0
fi
CREATIVE_NAME="$1"
CREATIVE_FILE="creatives/${CREATIVE_NAME}.yaml"
if [ ! -f "$CREATIVE_FILE" ]; then
    echo "创意配置文件不存在: $CREATIVE_FILE"
    $VENV_PYTHON run_creative.py --list
    exit 1
fi
echo "启动创意: $CREATIVE_NAME"
$VENV_PYTHON run_creative.py "$CREATIVE_FILE"
