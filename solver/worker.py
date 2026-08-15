"""Claude Code worker（cairn 式 session + conclude 驱动）主类。

文件拆分（拆 171 行 worker.py 为 2 个模块）：
  worker.py      - 本文件：SessionWorker 主类（init/run/_conclude）+ build_worker 工厂
  worker_cli.py  - claude CLI 进程封装：_run_cli / _execute_argv / _conclude_argv / _env

学 cairn 的 claudecode 驱动（cairn-ref/.../adapters/claudecode.py + tasks/explore.py）：
- execute:  `claude --session-id <uuid> --dangerously-skip-permissions -p -- <prompt>`（prompt 走 stdin）
- 超时/非零退出/JSON 解析失败 → conclude 兜底: `claude -r <session> -p -- <conclude_prompt>`
  恢复会话强制回收已确认的 JSON 事实，partial 发现不丢。
- 会话文件落盘 ~/.claude/projects/<cwd-hash>/<sid>.jsonl，增量写入，被杀也能恢复。

返回结构化 dict（accepted/kind/data/raw/source/error），不再抛异常丢 stdout。

⚠️ prompt 必须走 stdin（communicate(prompt) 自动写 stdin+close）：`stdin=PIPE` 但不喂
数据 → claude 报 "Input must be provided either through stdin or as a prompt argument" 退出。
"""
from __future__ import annotations

import logging

from solver.worker_cli import CliRunnerMixin, _stderr_snippet

LOG = logging.getLogger("solver.worker")


class SessionWorker(CliRunnerMixin):
    """cairn 式 claude CLI worker：session + conclude 兜底 + 结构化返回。

    run(prompt, phase=..., ...) -> dict
      成功: {accepted:True, kind:"fact|complete|intents|noop", data, session,
             raw, source:"execute|conclude", error:None, payload}
      失败: {accepted:False, kind:"failed|rejected", data:None, session,
             raw, source, error:"原因", payload}
    conclude_prompt 为 None（reason 用）时失败即返回，不做兜底。

    多重继承 CliRunnerMixin（cli 进程封装）—— 直接放 class 头上，不在 __init__ 里 hack。
    """

    def __init__(self, cfg: dict, timeout: float | None = None):
        m = cfg.get("model", {})
        self.base_url = m.get("base_url", "")
        self.api_key = m.get("api_key", "")
        self.model = m.get("model", "deepseek-v4-flash")
        scfg = cfg.get("solver", {})
        self.cli_path = scfg.get("cli_path", "claude")
        self.explore_timeout = float(scfg.get("explore_timeout", 300) or 300)
        self.bootstrap_timeout = float(scfg.get("bootstrap_timeout", 300) or 300)
        self.reason_timeout = float(scfg.get("reason_timeout", 120) or 120)
        self.conclude_timeout = float(scfg.get("conclude_timeout", 90) or 90)
        self.max_turns = int(scfg.get("max_turns", 40) or 40)

    def prepare_session(self) -> str:
        import uuid
        return str(uuid.uuid4())

    # ---------- 主入口 ----------
    def run(self, prompt: str, *, phase: str = "explore",
            allow_tools: bool = True, turns: int | None = None,
            timeout: float | None = None, session: str | None = None,
            conclude_prompt: str | None = None,
            validator_kwargs: dict | None = None) -> dict:
        """执行一次 + 失败 conclude 兜底。返回结构化 dict。"""
        from solver.contracts import parse_json_output, validate_for_phase
        session = session or self.prepare_session()
        exec_timeout = timeout or getattr(self, f"{phase}_timeout", self.explore_timeout)
        turns = turns or self.max_turns

        r = self._run_cli(self._execute_argv(session, allow_tools=allow_tools, turns=turns),
                          prompt, exec_timeout)
        raw = r["stdout"]
        if r["timed_out"] or r["returncode"] != 0:
            reason = "timeout" if r["timed_out"] else f"rc={r['returncode']} stderr={_stderr_snippet(r['stderr'])}"
            return self._conclude(session, phase, conclude_prompt, turns, raw, reason)
        try:
            payload = parse_json_output(raw)
            kind, data = validate_for_phase(phase, payload, **(validator_kwargs or {}))
            if kind == "rejected":
                return {"accepted": False, "kind": "rejected", "data": None,
                        "session": session, "raw": raw, "source": "execute",
                        "error": "rejected", "payload": payload}
            return {"accepted": True, "kind": kind, "data": data, "session": session,
                    "raw": raw, "source": "execute", "error": None, "payload": payload}
        except Exception as exc:
            return self._conclude(session, phase, conclude_prompt, turns, raw,
                                  f"execute parse: {exc}")

    def _conclude(self, session: str, phase: str, conclude_prompt: str | None,
                  turns: int, raw: str, reason: str) -> dict:
        """conclude 兜底：-r 恢复会话，强制收 JSON。conclude_prompt 为 None 则直接失败。"""
        from solver.contracts import parse_json_output, validate_for_phase
        if not conclude_prompt:
            return {"accepted": False, "kind": "failed", "data": None,
                    "session": session, "raw": raw, "source": "execute",
                    "error": reason, "payload": None}
        cr = self._run_cli(self._conclude_argv(session, turns=turns),
                           conclude_prompt, self.conclude_timeout)
        if cr["timed_out"] or cr["returncode"] != 0:
            err = "timeout" if cr["timed_out"] else f"rc={cr['returncode']} stderr={_stderr_snippet(cr['stderr'])}"
            return {"accepted": False, "kind": "failed", "data": None,
                    "session": session, "raw": cr["stdout"], "source": "conclude",
                    "error": f"{reason}; conclude failed ({err})", "payload": None}
        try:
            payload = parse_json_output(cr["stdout"])
            kind, data = validate_for_phase(phase, payload)
            if kind == "rejected":
                return {"accepted": False, "kind": "rejected", "data": None,
                        "session": session, "raw": cr["stdout"], "source": "conclude",
                        "error": "rejected", "payload": payload}
            return {"accepted": True, "kind": kind, "data": data, "session": session,
                    "raw": cr["stdout"], "source": "conclude",
                    "error": None, "payload": payload}
        except Exception as exc:
            return {"accepted": False, "kind": "failed", "data": None,
                    "session": session, "raw": cr["stdout"], "source": "conclude",
                    "error": f"{reason}; conclude parse: {exc}", "payload": None}


def build_worker(cfg: dict):
    """按 config.solver.worker 构建 worker。claude → SessionWorker；其它 → None(api 直连兜底)。"""
    wt = cfg.get("solver", {}).get("worker", "claude")
    if wt == "claude":
        return SessionWorker(cfg)
    return None
