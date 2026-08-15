"""SolverLoop reason 阶段：读图规划方向 + 过早放弃兜底。

从原 loop.py 抽出 _reason_once / _intents_to_decision / _fallback_intent。
"""
from __future__ import annotations

import logging

LOG = logging.getLogger("solver.reason")


class ReasonMixin:
    """Reason 阶段 mixin：cairn 流程的"读图规划方向"。"""
    code: str
    graph: object
    worker: object
    llm: object
    min_rounds: int
    reason_max_intents: int
    _reason_prompt: callable
    _intents_to_decision: callable
    _fallback_intent: callable

    def _intents_to_decision(self, intents: list) -> list[tuple[str, list[str], str]]:
        """intents 列表 → [(desc, from_facts, priority), ...]，高优先级排前。"""
        known = {f["id"] for f in self.graph.facts}
        out: list[tuple[str, list[str], str]] = []
        for it in intents[:5]:
            desc = it.get("description", "")
            priority = it.get("priority", "normal")
            frm = [f for f in it.get("from", []) if f in known and f != "goal"]
            if not frm:
                frm = ["origin"]
            if desc:
                out.append((desc, frm, priority))
        prio_map = {"high": 0, "normal": 1, "low": 2}
        out.sort(key=lambda x: prio_map.get(x[2], 1))
        return out

    def _reason_once(self):
        """一次 Reason。返回 'complete' / 'noop' / [(desc, from_facts, priority), ...]

        ③记录思路：log 出 AI 的 analysis（复盘/瓶颈/空档）。
        """
        if self.worker:
            try:
                res = self.worker.run(self._reason_prompt(), phase="reason",
                                      allow_tools=False, turns=3,
                                      timeout=getattr(self.worker, "reason_timeout", 120),
                                      conclude_prompt=None,  # reason 不做兜底，快
                                      validator_kwargs={
                                          "open_intents_empty": not bool(self.graph.open_intents()),
                                          "max_intents": self.reason_max_intents})
            except Exception as exc:
                LOG.warning("[%s] Reason 异常，视为 noop: %s", self.code, exc)
                return "noop"
            if not isinstance(res, dict):
                LOG.warning("[%s] Reason worker 非 SessionWorker 结果，视为 noop", self.code)
                return "noop"
            if not res["accepted"]:
                return "noop"
            analysis = (res.get("payload") or {}).get("analysis", "")
            if analysis:
                LOG.info("  └ 思考过程[%s]: %s", self.code, analysis.replace("\n", " ")[:400])
            kind = res["kind"]
            if kind == "complete":
                LOG.info("[%s] Reason → complete", self.code)
                return "complete"
            if kind == "noop":
                LOG.info("[%s] Reason → noop", self.code)
                return "noop"
            intents = res["data"] or []
            if not intents:
                LOG.info("[%s] Reason → noop", self.code)
                return "noop"
            return self._intents_to_decision(intents)

        # ---- api 直连兜底 ----
        text = self.llm.complete_text("", self._reason_prompt())
        if not text.strip():
            LOG.warning("[%s] Reason 无输出（LLM 失败？），视为 noop", self.code)
            return "noop"
        LOG.info("[%s] Reason 原始输出: %s", self.code, text.replace("\n", " ")[:500])
        parsed = self.llm.parse_json(text) or {}
        analysis = parsed.get("analysis") or ""
        if analysis:
            LOG.info("  └ 思考过程[%s]: %s", self.code, analysis.replace("\n", " ")[:400])
        data = parsed.get("data") or {}
        if data.get("complete"):
            LOG.info("[%s] Reason → complete", self.code)
            return "complete"
        intents = data.get("intents") or []
        if not intents:
            LOG.info("[%s] Reason → noop", self.code)
            return "noop"
        return self._intents_to_decision(intents)

    def _fallback_intent(self, round_no: int) -> list[tuple[str, list[str], str]]:
        """Reason 返回 noop 但轮数不足时，基于已有 facts 生成"继续深入"方向，防过早放弃。

        从图里找线索（发现的端点/403/302/登录页/受限目录），提示 AI 继续绕访问控制/深挖登录。
        """
        leads = []
        for f in self.graph.facts:
            c = (f.get("content") or "")[:300]
            if any(k in c for k in ("403", "302", "admin", "login", "登录", "受限",
                                    "forbidden", "denied", "api", "flag", "upload",
                                    "config", ".php", "WAF", "filter", "bypass")):
                leads.append(f["id"])
        frm = leads[:3] or ["origin"]
        desc = ("继续深挖已发现的线索（受限端点/登录/目录）：尝试访问控制绕过"
                "（HTTP 方法 OPTIONS/PUT/TRACE、编码路径、自定义头 X-Forwarded/X-Original-URL、"
                "绝对 URI、大小写），深入登录/上传/配置功能找注入或默认凭证。"
                "不要因为 403/302 就放弃——那通常是下一步的入口。")
        LOG.info("[%s] round %d < min_rounds=%d，noop 转继续: %s",
                 self.code, round_no, self.min_rounds, desc[:80])
        return [(desc, frm, "high")]
