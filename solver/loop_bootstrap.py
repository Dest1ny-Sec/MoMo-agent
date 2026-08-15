"""SolverLoop bootstrap 阶段：直接尝试（cairn 流程的第一步）。

从原 loop.py 抽出 _bootstrap()。
"""
from __future__ import annotations

import logging

LOG = logging.getLogger("solver.bootstrap")


class BootstrapMixin:
    """Bootstrap 阶段 mixin：直接尝试抓 flag / 拿信息，结果写回 graph。"""
    code: str
    graph: object  # Graph
    worker: object  # SessionWorker or None
    llm: object    # LLMClient
    explore_max_turns: int
    _scan_session_result: callable
    _scan_agentic_result: callable
    _report_flags: callable
    _bootstrap_prompt: callable
    _bootstrap_conclude_prompt: callable

    def _bootstrap(self) -> None:
        LOG.info("[%s] bootstrap 直接尝试", self.code)
        if self.worker:
            session = self.worker.prepare_session()
            try:
                res = self.worker.run(self._bootstrap_prompt(session), phase="bootstrap",
                                      allow_tools=True,
                                      conclude_prompt=self._bootstrap_conclude_prompt(session))
            except Exception as exc:
                LOG.warning("[%s] bootstrap worker 异常，降级 api: %s", self.code, exc)
                res = None
            if isinstance(res, dict):
                self._scan_session_result(res, session)
                if res["accepted"] and res["kind"] in ("fact", "complete"):
                    d = res["data"]
                    desc = d.get("fact_description", "") if isinstance(d, dict) else ""
                    if desc:
                        self.graph.add_fact(desc, "bootstrap")
                        self.graph.save()
                        LOG.info("[%s] bootstrap fact: %s", self.code, desc[:100])
            else:
                LOG.warning("[%s] bootstrap worker 非 SessionWorker 结果，跳过 fact", self.code)
        else:
            # ⚠️ 2026-08-13 evidence 落盘：让 cairn 扫到 flag
            ev_dir = self.ws / "evidence" / "api"
            r = self.llm.agentic("", self._bootstrap_prompt("api"), max_turns=self.explore_max_turns, evidence_dir=ev_dir)
            self._scan_agentic_result(r)
            text = r.get("text", "")
            # ⚠️ 2026-08-13 移除 bootstrap 末尾的 self._report_flags(text)：
            # 之前 deepseek 在 LLM 文本里编 UUID flag{...}，_report_flags 写入
            # flags_found.jsonl → cairn 30s 同步 → 平台拒收浪费配额。bootstrap
            # 阶段 flag 提取完全交给 _scan_agentic_result（只信 command output）。
            fact = self.llm.parse_json(text)
            desc = ""
            if isinstance(fact, dict):
                desc = (fact.get("data") or {}).get("description", "")
            if desc:
                self.graph.add_fact(desc, "bootstrap")
                self.graph.save()
                LOG.info("[%s] bootstrap fact: %s", self.code, desc[:100])
        LOG.info("[%s] bootstrap 完成", self.code)
