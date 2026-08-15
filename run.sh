#!/usr/bin/env bash
# Luvvv-agent 启动（重构后：cairn 式图搜索，只连真实 TSec 平台）
# 用法:
#   ./run.sh real        # 连真实 TSec Benchmark（自动 source .env，需连 VPN）
#   ./run.sh check       # 只做 VPN + adapter 连通性预检
#   ./run.sh vpn start   # 启 VPN；./run.sh vpn status / stop
set -e
cd "$(dirname "$0")"

# 加载 .env（如果存在）；不覆盖已有 shell 环境变量
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  echo "[env] 已加载 .env"
fi

case "${1:-real}" in
  real)
    # 跑分前快速检查 VPN 通不通
    if ! curl -s --max-time 3 http://10.0.100.58 >/dev/null 2>&1; then
      echo "⚠️  警告: VPN 预检地址不可达 (http://10.0.100.58)"
      echo "   若已连 VPN 仍不通，检查 config.json 的 vpn.precheck_url"
      echo "   强行跑分可以 5s 内 Ctrl-C 取消"
    else
      echo "[vpn] 预检通过"
    fi
    # 清理上次 run 的 workspace（防残留 flags/进度污染本轮；保留 metrics/ 战绩）
    if [ -d workspace ]; then
      echo "[clean] 清理上次 run 的 workspace ..."
      rm -rf workspace/*
      echo "[clean] 完成"
    fi
    shift  # 跳过 "real" 子命令，剩余参数传给 main.py
    python3 -m orchestrator.main --no-precheck "$@"
    ;;
  check)
    echo ">>> 预检: VPN + adapter 连通性"
    python3 -m orchestrator.main --check-only
    ;;
  vpn)
    shift
    sudo ./scripts/connect_vpn.sh "${1:-start}"
    ;;
  *)
    echo "用法: ./run.sh [real|check|vpn start|stop|status]"; exit 1;;
esac
