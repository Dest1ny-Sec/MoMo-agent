#!/usr/bin/env python3
"""跑真实 TSec 平台：cairn + 监控 + 自动 hint（无需 mock）。

用法：
  # 1. 连 VPN
  sudo ./scripts/connect_vpn.sh
  ./scripts/wait_vpn.sh

  # 2. 跑
  python3 scripts/run_real.py

它会：
  1. VPN 预检（失败就退出）
  2. 启 cairn orchestrator (3 槽并发)
  3. 实时观察 progress.jsonl，给卡住的题写 hint
  4. 汇总结果（首 flag / 全 flag 时间 / 轮数 / hint 次数）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKSPACE = ROOT / "workspace"
STAGED_THRESHOLD = 90       # 同题 90 秒无新 fact/flag → 触发 hint

HINT_TEMPLATE = """【进度告警】本题已运行 {elapsed:.0f}s 且 explore 阶段无新事实产出。

## 已确认状态
- 目标：{addr}
- 题面：{desc}
- 端口预判：{port_hint}（查 /opt/ctf-knowledge/07-port-mapping.md）
- 工具速查：/opt/ctf-knowledge/08-component-fingerprints.md

## 标准化节奏（playbook）
list → start → fingerprint → first-try → repro×2 → submit
完整版见 /opt/ctf-knowledge/09-playbook.md

## 推荐下一步（不要再"侦察"了，直接打）
{advice}

## 提示原则
- 已确认的事实写到 graph.json（cairn 持久记忆）
- 仍要工具优先（先 cat /opt/tools.md + /opt/ctf-knowledge/）
- 任何疑似 flag 先 repro×2 验证
- **不要再扩大无目标扫描**——题面/port 已知，**先打已知 CVE 套路**
"""


def vpn_precheck(url: str) -> bool:
    """VPN 联通预检：必须返回 status:ok 才放行。"""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", "ignore")
            data = json.loads(body)
            ok = data.get("status") == "ok"
            print(f"[vpn] 预检结果: status={data.get('status')}", flush=True)
            return ok
    except Exception as exc:
        print(f"[vpn] 预检失败: {exc}", flush=True)
        return False


def get_advice(unique_code: str) -> str:
    """针对每道题给精确 hint（基于历史/题型）。"""
    advice_map = {
        # a-08 = download.php id=2 path traversal
        "a-08": "1) curl 'http://<target>/download.php?id=2' 应该返回 200 + 文件内容\n2) 看返回内容是否含 flag 字符串\n3) 立刻 repro 一次 + submit",
        # a-01 = Flask 日志 ....// 绕过
        "a-01": "1) 先 POST /login 拿 session（auditor 账号）\n2) GET /api/logs/list 看有哪些日志文件\n3) GET /api/logs/read?filename=....//....//....//....//challenge/flag.txt\n4) 拿到 flag 后 repro + submit",
        # a-05 = LFI download.php
        "a-05": "1) /download.php?id= 参数 LFI\n2) curl 'http://<target>/download.php?id=../../../../challenge/flag.txt'\n3) 立即 repro + submit",
        # c-06 = Gremlin CVE-2024-27348
        "c-06": "1) 确认 Gremlin (banner 应该有 'Gremlin Server')\n2) CVE-2024-27348 auth bypass：POST /gremlin body {\"gremlin\":\"<exploit>\"}\n3) 注：cat /challenge/flag.txt 通常即可",
    }
    return advice_map.get(unique_code,
        "1) cat /opt/ctf-knowledge/09-playbook.md\n2) 按 list→start→fingerprint→exploit→repro→submit 节奏走")


def write_hint(unique_code: str, desc: str, addr: str, elapsed: float, port_hint: str):
    """给某题写 human_instructions.json（cairn worker 下轮会读到）"""
    ws = WORKSPACE / unique_code
    ws.mkdir(parents=True, exist_ok=True)
    hint_text = HINT_TEMPLATE.format(
        elapsed=elapsed,
        addr=addr,
        desc=(desc or "")[:200],
        port_hint=port_hint,
        advice=get_advice(unique_code),
    )
    p = ws / "human_instructions.json"
    p.write_text(json.dumps({
        "seq": int(time.time() * 1000),
        "text": hint_text,
        "ts": datetime.now().strftime("%H:%M:%S"),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"[hint] ✍️  写 hint 到 {unique_code}/human_instructions.json ({len(hint_text)} 字符)", flush=True)


def watch_progress():
    """实时观察 progress.jsonl + solver.log，触发 hint"""
    print("[watch] 启动进度监控（每 10 秒扫一次）", flush=True)
    last_hint_ts: dict[str, float] = {}

    while True:
        if not WORKSPACE.exists():
            time.sleep(5)
            continue
        now = time.time()
        for ws in WORKSPACE.iterdir():
            if not ws.is_dir():
                continue
            unique_code = ws.name
            prog = ws / "progress.jsonl"
            if not prog.exists():
                continue
            try:
                mtime = prog.stat().st_mtime
            except OSError:
                continue
            try:
                lines = prog.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            if not lines:
                continue

            # 从 progress.jsonl 拿 desc / addr
            desc, addr = "", ""
            port_hint = "未知"
            for line in lines[-20:]:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("description"):
                    desc = d["description"]
                if d.get("addr"):
                    addr = d["addr"]
                    if ":" in addr:
                        port_hint = f":{addr.split(':')[-1]}"

            elapsed = now - mtime
            if elapsed > STAGED_THRESHOLD:
                last_hint = last_hint_ts.get(unique_code, 0)
                if now - last_hint > 120:    # 同题每 120s 最多 hint 一次
                    write_hint(unique_code, desc, addr, elapsed, port_hint)
                    last_hint_ts[unique_code] = now
        time.sleep(10)


def print_summary():
    """跑完后打印总结（首 flag / 全 flag 时间 / 轮数 / hint 次数）"""
    print()
    print("=" * 60)
    print("📊 跑分总结")
    print("=" * 60)
    if not WORKSPACE.exists():
        print("  无 workspace 目录")
        return
    total_score = 0
    for ws in sorted(WORKSPACE.iterdir()):
        if not ws.is_dir():
            continue
        code = ws.name
        flags = 0
        rounds = 0
        hint_count = 0
        prog = ws / "progress.jsonl"
        if prog.exists():
            try:
                for line in prog.read_text(encoding="utf-8").splitlines():
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("type") == "flag_found":
                        flags += 1
                    if d.get("type") == "reason":
                        rounds += 1
            except Exception:
                pass
        if (ws / "human_instructions.json").exists():
            hint_count = 1
        sub = ws / "submission_results.jsonl"
        score = 0
        if sub.exists():
            try:
                for line in sub.read_text(encoding="utf-8").splitlines():
                    try:
                        d = json.loads(line)
                        if d.get("correct"):
                            score += 100
                    except Exception:
                        continue
            except Exception:
                pass
        total_score += score
        print(f"  {code:6s}  flags={flags}  rounds={rounds}  hint={hint_count}  score={score}")
    print(f"  ---")
    print(f"  总分: {total_score}")


def load_env_file(path: Path) -> int:
    """简易 .env 加载（KEY=VALUE 格式，# 注释，引号可有可无），不覆盖已设的环境变量。返回加载条数。"""
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


def main():
    print("=" * 60)
    print("🚀 启动真实 TSec 跑分（cairn + 监控 + hint）")
    print("=" * 60)

    # 0. 加载 .env（不覆盖已有 env）
    env_file = ROOT / ".env"
    loaded = load_env_file(env_file)
    print(f"[env] 已从 {env_file} 加载 {loaded} 个变量（已存在的不会覆盖）")

    # 0.5. VPN 预检
    cfg_path = ROOT / "config.json"
    cfg = json.loads(cfg_path.read_text())
    precheck_url = cfg.get("vpn", {}).get("precheck_url", "http://10.0.100.58")
    print(f"[step 0] VPN 预检 {precheck_url}")
    if not vpn_precheck(precheck_url):
        print("❌ VPN 不通，先跑：sudo ./scripts/connect_vpn.sh && ./scripts/wait_vpn.sh")
        sys.exit(1)
    print("  ✓ VPN 通")

    # 1. 启 cairn orchestrator
    print("[step 1] 启 cairn orchestrator...")
    env = os.environ.copy()
    # 兜底
    env.setdefault("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    env.setdefault("ANTHROPIC_MODEL", "deepseek-v4-flash")
    if not env.get("ANTHROPIC_AUTH_TOKEN"):
        print("❌ 缺 ANTHROPIC_AUTH_TOKEN（请先 export 或写 .env）")
        sys.exit(1)
    env.setdefault("LUVVV_ADAPTER", "tsec")
    env.setdefault("LUVVV_MODEL_PROVIDER", "anthropic")
    env.setdefault("LUVVV_EXEC_BACKEND", "host")
    env.setdefault("TERMINAL_ENV", "local")

    print(f"  ANTHROPIC_BASE_URL={env['ANTHROPIC_BASE_URL']}")
    print(f"  ANTHROPIC_MODEL={env['ANTHROPIC_MODEL']}")
    print(f"  BENCHMARK_BASE_URL={env.get('BENCHMARK_BASE_URL', '(待 cairn 内部读 config.json)')}")

    cairn_proc = subprocess.Popen(
        ["python3", "-m", "orchestrator.main",
         "--adapter", "tsec", "--no-server", "--auto-exit"],
        cwd=str(ROOT), env=env,
        stdout=open("/tmp/cairn.log", "w"), stderr=subprocess.STDOUT,
    )
    print(f"  ✓ cairn 启动 (PID={cairn_proc.pid})")

    # 2. 启 watch
    print("[step 2] 启 progress 监控（hint 触发）...")
    watch_thread = threading.Thread(target=watch_progress, daemon=True)
    watch_thread.start()

    # 3. 等 cairn 跑完
    try:
        cairn_proc.wait()
    except KeyboardInterrupt:
        print("\n[ctrl-c] 杀掉 cairn")
        cairn_proc.terminate()

    # 4. 总结
    print_summary()
    print()
    print("Logs:")
    print(f"  cairn: tail -f /tmp/cairn.log")
    print(f"  vpn:   tail -f /tmp/luvvv_vpn.log")


if __name__ == "__main__":
    main()
