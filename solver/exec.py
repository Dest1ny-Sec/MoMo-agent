"""命令执行：在容器内直接跑 bash（本地后端，无需 docker-in-docker）。

供 Explore/Bootstrap 的 bash 工具调用。返回结构化结果给 LLM 回填。
"""
from __future__ import annotations

import re
import subprocess

# 输出截断上限（避免把 LLM 上下文撑爆）
MAX_OUTPUT = 12000

# 禁词（soft-hard）：题目说"不要大规模端口扫描"+"不要 ffuf 大字典全扫"
# 规则：nmap 必须 -sV + -p 范围 ≤ 100；ffuf 不准用大字典（用 knowledge 常见端点 + curl）
_BLOCKED_PATTERNS = [
    # nmap 必须有 -sV，否则警告（题目要服务识别）
    (re.compile(r"\bnmap\b(?![^\n|;&]*-sV)", re.I), "nmap 调用必须加 -sV（题目要服务识别）：nmap -sV -p 80,8080,9100 <target>"),
    # nmap -p 范围 > 100 端口 = 浪费
    (re.compile(r"\bnmap\b[^\n|;&]{0,200}-p\s+1-\d{4,}\b", re.I), "nmap 端口范围太大（>100）。改用 nmap -sV -p 80,8080,9100,5005,1099,2375,9200,6379 <target>（≤ 10 个常见端口）"),
    (re.compile(r"\bnmap\b[^\n|;&]{0,200}-p-\b", re.I), "nmap -p- 全端口被禁用（题目说不要大规模端口扫描）。改用 nmap -sV -p 80,8080,9100 <target>"),
    # ffuf -w *big* 或大字典路径
    (re.compile(r"\bffuf\b[^\n|;&]{0,40}-w\s+[^\s|;&]*big[^\s|;&]*", re.I), "ffuf 大字典被禁用（题目说不要 ffuf）。改用 knowledge/07-port-mapping.md 的常见端点表 + 单个 curl"),
    (re.compile(r"\bffuf\b[^\n|;&]{0,40}-w\s+/usr/share/(?:seclists|wordlists)/[^\s|;&]+\.txt", re.I), "ffuf 大字典被禁用。改用 knowledge/07-port-mapping.md + curl"),
]


def run_command(cmd: str, timeout: int = 120, cwd: str | None = None) -> dict:
    """执行一条 bash 命令。返回 {output, exit_code, timed_out}。"""
    if not cmd or not cmd.strip():
        return {"output": "", "exit_code": 0, "timed_out": False}
    # 禁词拦截（hard block）
    for pat, msg in _BLOCKED_PATTERNS:
        if pat.search(cmd):
            return {
                "output": f"[BLOCKED] {msg}\n命令: {cmd[:200]}",
                "exit_code": -1, "timed_out": False,
            }
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=cwd, executable="/bin/bash", errors="replace",
        )
        out = (proc.stdout or "").strip()
        if proc.stderr:
            out += "\n[stderr]\n" + proc.stderr.strip()
        return {"output": out[:MAX_OUTPUT], "exit_code": proc.returncode,
                "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        partial = ""
        if isinstance(exc.stdout, bytes):
            partial = exc.stdout.decode("utf-8", "replace")
        elif exc.stdout:
            partial = str(exc.stdout)
        return {"output": f"{partial}\n[命令超时 {timeout}s，请缩小范围/换轻量方法]",
                "exit_code": -1, "timed_out": True}
    except Exception as exc:  # noqa: BLE001
        return {"output": f"[执行失败] {exc}", "exit_code": -1, "timed_out": False}
