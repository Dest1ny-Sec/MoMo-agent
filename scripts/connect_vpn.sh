#!/bin/bash
# 连接 TSec 跑分 VPN（后台 openvpn + 证书认证）
#
# 用法：
#   sudo ./scripts/connect_vpn.sh
# 作用：后台启 openvpn，写 PID 到 /tmp/luvvv_vpn.pid，日志 /tmp/luvvv_vpn.log
#
# 断 VPN：
#   sudo kill $(cat /tmp/luvvv_vpn.pid)
set -e

OVPN="${OVPN:-/Users/destiny/Downloads/task_ljPV9AdAPF37_vpn_config.ovpn}"
LOG="/tmp/luvvv_vpn.log"
PIDFILE="/tmp/luvvv_vpn.pid"

# 已经在跑就别再启
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "✓ VPN 已在跑 (PID=$PID)，跳过"
        echo "  断连：sudo kill $PID"
        exit 0
    fi
    rm -f "$PIDFILE"
fi

if [ ! -f "$OVPN" ]; then
    echo "❌ .ovpn 不存在: $OVPN"
    exit 1
fi

echo "启动 openvpn (后台)..."
echo "  config: $OVPN"
echo "  log:    $LOG"
echo "  pid:    $PIDFILE"

# --daemon 后台；--writepid 把 PID 写到文件；--log 写日志
openvpn \
    --config "$OVPN" \
    --daemon \
    --log "$LOG" \
    --writepid "$PIDFILE"

# 等几秒看是否启动成功
sleep 3
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "✓ openvpn 启动 (PID=$PID)"
        echo "  日志: tail -f $LOG"
        echo "  断连: sudo kill $PID"
        exit 0
    fi
fi

echo "❌ openvpn 启动失败，看 $LOG"
tail -30 "$LOG" 2>/dev/null || true
exit 1
