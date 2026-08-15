"""Luvvv-agent 主入口：VPN 预检 → 启动面板 → 跑分调度。

用法：
    python3 -m orchestrator.main            # 全自动跑分（连真实 TSec 平台）
    python3 -m orchestrator.main --check-only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request

from luvvv_common import ROOT, configure_logging, load_config
from orchestrator.metrics import Metrics
from orchestrator.scheduler import Scheduler
from orchestrator.server import start_status_server
from orchestrator.status import StatusStore
from adapters.base import build_adapter
from adapters.errors import AuthError, PlatformError

LOG = logging.getLogger("main")


def vpn_precheck(url: str) -> bool:
    """VPN 联通预检：必须返回 status:ok 才放行。"""
    LOG.info("VPN 联通预检 %s", url)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", "ignore")
            data = json.loads(body)
            ok = data.get("status") == "ok"
            LOG.info("VPN 预检结果: status=%s", data.get("status"))
            return ok
    except Exception as exc:
        LOG.error("VPN 预检失败: %s", exc)
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", help="覆盖 platform.adapter（默认 tsec）")
    parser.add_argument("--check-only", action="store_true", help="只做 VPN 预检")
    parser.add_argument("--no-precheck", action="store_true", help="跳过 VPN 预检(测试用)")
    parser.add_argument("--auto-exit", action="store_true", help="跑完 1 秒后自动退出（脚本/CI 用）")
    parser.add_argument("--no-server", action="store_true", help="不启前端面板（托管模式专用）")
    args = parser.parse_args()

    configure_logging()
    cfg = load_config()
    store = StatusStore()
    metrics = Metrics(ROOT)

    # 覆盖 adapter
    if args.adapter:
        cfg.setdefault("platform", {})["adapter"] = args.adapter

    svr = cfg["server"]
    if args.no_server:
        LOG.info("已禁用前端面板 (--no-server)，托管模式专用")
    else:
        start_status_server(store, svr["host"], int(svr["port"]))

    # VPN 预检
    if not args.no_precheck:
        vpn_url = cfg["vpn"]["precheck_url"]
        ok = vpn_precheck(vpn_url)
        store.update(phase="vpn_check", vpn_ok=ok)
        if not ok:
            print("\nVPN检测未通过，请检查靶场VPN网络配置\n")
            print("提示：预检地址 http://10.0.100.58 需在 VPN 网络内可达且返回 status:\"ok\"")
            store.log_event("VPN 预检未通过，流程中断")
            sys.exit(1)
        store.log_event("VPN 预检通过")
    else:
        store.update(vpn_ok=True)
        store.log_event("已跳过 VPN 预检（测试模式）")
    if args.check_only:
        print("VPN 预检通过 ✓")
        return

    # 构建 adapter
    try:
        adapter = build_adapter(cfg)
    except ValueError as exc:
        print(f"\n[配置错误] {exc}\n")
        store.log_event(f"配置错误: {exc}")
        sys.exit(1)
    LOG.info("Platform adapter: %s", adapter.name)
    store.log_event(f"已加载平台适配器: {adapter.name}")

    scheduler = Scheduler(cfg, adapter, store, metrics)
    try:
        result = scheduler.run()
        print("\n=== 跑分结果 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        store.update(phase="finished")
    except KeyboardInterrupt:
        print("\n用户中断")
        store.update(phase="error")
    except AuthError as exc:
        print(f"\n[鉴权失败] {exc.message}")
        store.log_event(f"鉴权失败: {exc.message}")
        store.update(phase="error")
    except PlatformError as exc:
        print(f"\n[平台错误 {exc.code}] {exc.message}")
        store.log_event(f"平台错误 {exc.code}: {exc.message}")
        store.update(phase="error")

    # 跑分结束后保持面板在线（默认行为，Ctrl-C 退出）
    # --auto-exit：跑完 1 秒后自动退出（适合脚本/CI）
    import time
    if getattr(args, "auto_exit", False):
        print(f"\n跑分结束（--auto-exit 模式 1 秒后退出）")
        time.sleep(1)
    else:
        print(f"\n✓ 跑分结束。面板仍在线: http://{svr['host']}:{svr['port']}")
        print("  Ctrl-C 退出，或用 --auto-exit 跑完即退")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n已退出")


if __name__ == "__main__":
    main()
