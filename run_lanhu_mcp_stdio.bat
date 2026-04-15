@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not defined LANHU_MCP_USER_NAME set "LANHU_MCP_USER_NAME=Codex"
if not defined LANHU_MCP_USER_ROLE set "LANHU_MCP_USER_ROLE=开发"

set /p LANHU_COOKIE=<cookie

if not defined HTTP_TIMEOUT set "HTTP_TIMEOUT=8000"

set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "NO_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="
set "no_proxy="

set "PYTHON_BIN=%~dp0venv\Scripts\python.exe"
if not exist "%PYTHON_BIN%" (
    echo 错误: 未找到虚拟环境 Python: %PYTHON_BIN% >&2
    echo 请在当前目录重新创建并安装依赖: python -m venv venv ^&^& venv\Scripts\python -m pip install -r requirements.txt >&2
    exit /b 1
)

"%PYTHON_BIN%" "%~dp0lanhu_mcp_server.py"
