#!/bin/bash
# 等待 VPN 通（HTTP 探测内部网关）
#
# 用法：
#   ./scripts/wait_vpn.sh [timeout_sec]
#   VPN_CHECK_URL=... ./scripts/wait_vpn.sh
set -e

TIMEOUT="${1:-60}"
VPN_CHECK_URL="${VPN_CHECK_URL:-http://10.0.100.58}"

echo "等待 VPN 通 (URL=$VPN_CHECK_URL, timeout=${TIMEOUT}s)..."
for i in $(seq 1 "$TIMEOUT"); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "$VPN_CHECK_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" != "000" ] && [ "$HTTP_CODE" != "" ]; then
        echo "✓ VPN 通 (HTTP=$HTTP_CODE, ${i}s)"
        exit 0
    fi
    if [ $((i % 5)) -eq 0 ]; then
        echo "  等待中... ($i/${TIMEOUT}s)"
    fi
    sleep 1
done

echo "❌ VPN 等待超时 (${TIMEOUT}s)"
echo "  看日志: tail -f /tmp/luvvv_vpn.log"
echo "  手动测: curl -m 3 $VPN_CHECK_URL"
exit 1
