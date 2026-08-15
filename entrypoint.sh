#!/bin/sh
# Luvvv-agent 托管模式入口（重构后：cairn 式图搜索，不依赖 hermes）
# - 沙箱冷启动清理
# - 强制 tsec adapter、不启前端、跑完即退
# - LLM 配置直接由平台注入的环境变量 ANTHROPIC_* 提供（load_config 读取）

set -e

# 关键：清掉 daemon 注入的代理（沙箱内 127.0.0.1:7890 = clash 端口，访问不到）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY ftp_proxy FTP_PROXY
export no_proxy="*"
export NO_PROXY="*"

cd /app

echo "[entrypoint] === Luvvv-agent 托管模式启动（图搜索版）==="

# ===== 1. 冷启动清理 =====
rm -rf /app/workspace/*
rm -rf /app/logs
mkdir -p /app/workspace /app/logs /app/metrics
echo "[entrypoint] ✓ workspace/logs/metrics 已就绪"

# ===== 2. 校验关键环境变量 =====
missing=""
[ -z "$ANTHROPIC_AUTH_TOKEN" ] && missing="$missing ANTHROPIC_AUTH_TOKEN"
[ -z "$BENCHMARK_TOKEN" ] && missing="$missing BENCHMARK_TOKEN"
[ -z "$BENCHMARK_BASE_URL" ] && missing="$missing BENCHMARK_BASE_URL"
if [ -n "$missing" ]; then
    echo "[entrypoint] ⚠️  警告：以下环境变量未设置$missing"
    echo "  请在平台「运行时环境变量」面板配置（ANTHROPIC_AUTH_TOKEN 必填；BENCHMARK_* 平台自动注入）"
fi
if [ -z "$ANTHROPIC_BASE_URL" ]; then
    export ANTHROPIC_BASE_URL="http://api.deepseek.com.tsecbench.gw/anthropic"
    echo "[entrypoint] ⚠️  ANTHROPIC_BASE_URL 未设置，使用兜底网关: $ANTHROPIC_BASE_URL"
fi

# ===== 3. 启动主程序 =====
echo "[entrypoint] === 启动 orchestrator ==="
exec env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY -u ftp_proxy -u FTP_PROXY \
    python3 -m orchestrator.main \
        --adapter tsec \
        --no-precheck \
        --no-server \
        --auto-exit
