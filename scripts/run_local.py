#!/usr/bin/env python3
"""本地跑 cairn 完整流程：mock + cairn + 实时观察 + 自动 hint。

用法：
  # 1. 设置 key（任选一种）
  export ANTHROPIC_AUTH_TOKEN="sk-你的deepseek key"
  export BENCHMARK_BASE_URL="http://127.0.0.1:19900"

  # 2. 跑
  python3 scripts/run_local.py

它会：
  1. 启 mock 平台 (5 道题，端口 18080-18086)
  2. 启 cairn orchestrator (3 槽并发)
  3. 实时观察 progress.jsonl，给卡住的题写 hint
  4. 汇总结果（首 flag 时间 / 全 flag 时间 / 轮数 / hint 次数）
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
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


def get_challenge_desc(unique_code: str) -> str:
    """从 mock 题面读（直接 import 避免启动 mock）"""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from mini_tsec import CHALLENGES
        return CHALLENGES.get(unique_code, {}).get("description", "")
    except Exception:
        return ""


def get_port_hint(unique_code: str) -> str:
    """根据 unique_code 找端口（mock 已知）"""
    port_map = {
        "a-01": ":80 通用 Web / WAF",
        "a-05": ":80 通用 Web / WAF",
        "a-08": ":80 通用 Web / WAF",
        "a-13": ":80 通用 Web / WAF",
        "c-06": ":8080 图数据库 / GeoServer（注意 :8182=Gremlin）",
    }
    return port_map.get(unique_code, "未知")


def get_advice(unique_code: str) -> str:
    """针对每道题给精确 hint（基于 mini_tsec.CHALLENGES.vuln）"""
    advice_map = {
        "a-08": "1) GET /download.php?id=2 直接读 /challenge/flag.txt（无需 auth）\n2) curl 'http://127.0.0.1:18080/download.php?id=2' 应该拿到 flag\n3) 立刻 repro 一次 + submit",
        "a-01": "1) 先 POST /login auditor/任意密码（拿 session）\n2) GET /api/logs/list 看有什么日志\n3) GET /api/logs/read?filename=....//....//....//....//challenge/flag.txt\n4) 拿到 flag 后 repro + submit",
        "a-05": "1) /download.php?id= 参数有 LFI\n2) curl 'http://127.0.0.1:18082/download.php?id=../../../../challenge/flag.txt'\n3) 立即 repro + submit",
        "c-06": "1) 确认是 Gremlin (banner 'Gremlin Server')\n2) CVE-2024-27348 auth bypass\n3) POST /gremlin body {\"gremlin\":\"<exploit>\"}\n4) 注：mock 已简化，cat /challenge/flag.txt 即可",
        "a-13": "1) pydash 原型链污染\n2) GET /src?file=/challenge/flag.txt\n3) 关键参数：\n   - Cookie 用八进制编码 \\\\xxx 绕过\n   - pydash 用 . 分隔路径\n   - 要 \\\\ 绕过路径分隔符\n4) 拿到 flag 后 repro + submit",
    }
    return advice_map.get(unique_code, "1) cat /opt/ctf-knowledge/09-playbook.md\n2) 按 list→start→fingerprint→exploit→repro→submit 节奏走")


def write_hint(unique_code: str, elapsed: float):
    """给某题写 human_instructions.json（cairn worker 下轮会读到）"""
    ws = WORKSPACE / unique_code
    ws.mkdir(parents=True, exist_ok=True)
    desc = get_challenge_desc(unique_code)
    addr = "127.0.0.1:18xxx"  # mock 端口
    hint_text = HINT_TEMPLATE.format(
        elapsed=elapsed,
        addr=addr,
        desc=desc[:200],
        port_hint=get_port_hint(unique_code),
        advice=get_advice(unique_code),
    )
    p = ws / "human_instructions.json"
    p.write_text(json.dumps({
        "seq": int(time.time() * 1000),
        "text": hint_text,
        "ts": datetime.now().strftime("%H:%M:%S"),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"[hint] ✍️ 写 hint 到 {unique_code}/human_instructions.json ({len(hint_text)} 字符)", flush=True)


def watch_progress():
    """实时观察 progress.jsonl + solver.log，触发 hint"""
    print("[watch] 启动进度监控（每 10 秒扫一次）", flush=True)
    last_progress_ts: dict[str, float] = {}
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
            # 看 progress 最后事件
            try:
                lines = prog.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            if not lines:
                continue
            last_event_ts = mtime
            last_progress_ts[unique_code] = last_event_ts

            # 同题 90 秒无新进度 → 触发 hint
            elapsed = now - mtime
            if elapsed > STAGED_THRESHOLD:
                last_hint = last_hint_ts.get(unique_code, 0)
                if now - last_hint > 120:    # 同题每 120s 最多 hint 一次
                    write_hint(unique_code, elapsed)
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
        first_flag_sec = None
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
        # hint 计数
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
                            score += 100  # 简化：每 flag +100
                    except Exception:
                        continue
            except Exception:
                pass
        total_score += score
        print(f"  {code:5s}  flags={flags}  rounds={rounds}  hint={hint_count}  score={score}")
    print(f"  ---")
    print(f"  总分: {total_score}")


def main():
    if not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("❌ 缺 ANTHROPIC_AUTH_TOKEN（请先 export）")
        sys.exit(1)
    print("=" * 60)
    print("🚀 启动本地 cairn 跑分（mock + orchestrator + 监控）")
    print("=" * 60)

    # 1. 启 mock
    print("[step 1] 启 mock 平台...")
    mock_proc = subprocess.Popen(
        ["python3", str(ROOT / "scripts" / "mini_tsec.py")],
        stdout=open("/tmp/mini_tsec.log", "w"), stderr=subprocess.STDOUT,
    )
    time.sleep(2)
    if mock_proc.poll() is not None:
        print(f"❌ mock 启动失败，看 /tmp/mini_tsec.log")
        return
    print(f"  ✓ mock 启动 (PID={mock_proc.pid})")

    # 2. 设环境变量
    env = os.environ.copy()
    env["BENCHMARK_BASE_URL"] = "http://127.0.0.1:19900"
    env["BENCHMARK_TOKEN"] = "mock-token"
    env.setdefault("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    env.setdefault("ANTHROPIC_MODEL", "deepseek-v4-flash")
    env["LUVVV_ADAPTER"] = "tsec"
    env["LUVVV_MODEL_PROVIDER"] = "anthropic"
    env["LUVVV_EXEC_BACKEND"] = "host"
    env["TERMINAL_ENV"] = "local"

    # 3. 启 cairn orchestrator
    print("[step 2] 启 cairn orchestrator...")
    print(f"  ANTHROPIC_BASE_URL={env['ANTHROPIC_BASE_URL']}")
    print(f"  BENCHMARK_BASE_URL={env['BENCHMARK_BASE_URL']}")
    cairn_proc = subprocess.Popen(
        ["python3", "-m", "orchestrator.main",
         "--adapter", "tsec", "--no-precheck", "--no-server", "--auto-exit"],
        cwd=str(ROOT), env=env,
        stdout=open("/tmp/cairn.log", "w"), stderr=subprocess.STDOUT,
    )
    print(f"  ✓ cairn 启动 (PID={cairn_proc.pid})")

    # 4. 启 watch
    print("[step 3] 启 progress 监控（hint 触发）...")
    watch_thread = threading.Thread(target=watch_progress, daemon=True)
    watch_thread.start()

    # 5. 等 cairn 跑完
    try:
        cairn_proc.wait()
    except KeyboardInterrupt:
        print("\n[ctrl-c] 杀掉 cairn + mock")
        cairn_proc.terminate()
        mock_proc.terminate()

    # 6. 总结
    print_summary()
    print()
    print("Logs:")
    print(f"  mock:  tail -f /tmp/mini_tsec.log")
    print(f"  cairn: tail -f /tmp/cairn.log")


if __name__ == "__main__":
    import threading
    main()
