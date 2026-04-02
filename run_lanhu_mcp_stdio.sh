#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export LANHU_MCP_USER_NAME="${LANHU_MCP_USER_NAME:-Codex}"
export LANHU_MCP_USER_ROLE="${LANHU_MCP_USER_ROLE:-开发}"

export LANHU_COOKIE="$(< cookie)"

export HTTP_TIMEOUT="${HTTP_TIMEOUT:-8000}"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
unset http_proxy https_proxy all_proxy no_proxy
unset __PROXY_HTTP __PROXY_HTTPS __PROXY_SOCKS

# Use the repo-local virtualenv directly so the script keeps working after moves.
PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  echo "错误: 未找到可执行的虚拟环境 Python: $PYTHON_BIN" >&2
  echo "请在当前目录重新创建并安装依赖: python3 -m venv venv && ./venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/lanhu_mcp_server.py"
