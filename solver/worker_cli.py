"""Claude CLI 进程封装：_run_cli / _execute_argv / _conclude_argv / _env。

从原 worker.py 抽出：所有 spawn subprocess 跑 claude 的方法 + env 处理。

⚠️ prompt 走 stdin (communicate 自动写 stdin+close) — 不喂数据会触发 claude 报
"Input must be provided either through stdin or as a prompt argument" 退出。
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess

LOG = logging.getLogger("solver.worker.cli")

_PROXY_KEYS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
               "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY")


def _stderr_snippet(err: str, n: int = 200) -> str:
    """压缩 claude stderr 到一行片段，用于错误信息（rc=1 不再盲猜）。"""
    err = (err or "").strip().replace("\n", " ")
    return (err[:n] + "...") if len(err) > n else (err or "(无 stderr)")


class CliRunnerMixin:
    """Claude CLI 调用 mixin：被 SessionWorker 继承。"""
    cli_path: str
    base_url: str
    api_key: str
    model: str
    conclude_timeout: float
    explore_timeout: float

    def _env(self) -> dict:
        env = dict(os.environ)
        env["ANTHROPIC_BASE_URL"] = self.base_url or env.get("ANTHROPIC_BASE_URL", "")
        env["ANTHROPIC_AUTH_TOKEN"] = self.api_key or env.get("ANTHROPIC_AUTH_TOKEN", "")
        env["ANTHROPIC_MODEL"] = self.model or env.get("ANTHROPIC_MODEL", "")
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"  # 沙箱内无公网，禁遥测
        for k in _PROXY_KEYS:
            env.pop(k, None)  # 清掉 daemon 注入的 127.0.0.1:7890 代理
        # 剥离提交凭证：模型不得直接 curl 提交 flag（提交由 orchestrator 统一做）
        for k in list(env):
            if k.startswith("BENCHMARK_") or k.startswith("TSEC_"):
                env.pop(k, None)
        env["NO_PROXY"] = "*"
        env["no_proxy"] = "*"
        return env

    def _run_cli(self, argv: list[str], prompt: str, timeout: float) -> dict:
        """跑一次 claude。prompt 走 stdin。超时 SIGKILL 进程组（防 claude 的 bash 子进程残留）。"""
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                env=self._env(), start_new_session=True)
        try:
            out, err = proc.communicate(prompt, timeout=timeout)
            return {"returncode": proc.returncode, "stdout": out or "",
                    "stderr": err or "", "timed_out": False}
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            out, err = proc.communicate()
            return {"returncode": -9, "stdout": out or "",
                    "stderr": err or "", "timed_out": True}

    def _execute_argv(self, session: str, *, allow_tools: bool, turns: int) -> list[str]:
        argv = [self.cli_path, "--session-id", session]
        if allow_tools:
            argv += ["--dangerously-skip-permissions"]
        argv += ["-p", "--model", self.model, "--max-turns", str(turns),
                 "--output-format", "text"]
        return argv

    def _conclude_argv(self, session: str, *, turns: int) -> list[str]:
        return [self.cli_path, "-r", session, "--dangerously-skip-permissions",
                "-p", "--model", self.model, "--max-turns", str(turns),
                "--output-format", "text"]
