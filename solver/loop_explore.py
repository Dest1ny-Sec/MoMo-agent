"""SolverLoop explore 阶段：并行执行 intents，写回 graph。

从原 loop.py 抽出 _explore_one / _explore_intents。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from solver.loop_prompts import FLAG_RE, is_plausible_flag

LOG = logging.getLogger("solver.explore")


class ExploreMixin:
    """Explore 阶段 mixin：cairn 流程的"执行 intent 写回 fact/flag"。"""
    code: str
    cfg: dict
    ws: object  # Path
    graph: object
    worker: object
    llm: object
    parallel: int
    flags_found: set
    _explore_prompt: callable
    _explore_conclude_prompt: callable
    _scan_agentic_result: callable
    _scan_session_result: callable
    _report_flags: callable
    _prepare_session: callable

    def _prepare_session(self):
        return self.worker.prepare_session()

    def _explore_one(self, intent: dict) -> dict:
        """跑一个 intent 的 explore，返回 {desc, flags, success}。不改图（由 _explore_intents 统一应用）。"""
        LOG.info("[%s] explore %s: %s", self.code, intent["id"], intent.get("action", "")[:80])
        turns_map = self.cfg.get("solver", {}).get(
            "explore_turns_by_priority", {"high": 25, "normal": 12, "low": 6})
        prio = intent.get("priority", "normal")
        t = int(turns_map.get(prio, turns_map.get("normal", 12)))
        if self.worker:
            session = self._prepare_session()
            try:
                res = self.worker.run(self._explore_prompt(intent, session), phase="explore",
                                      allow_tools=True, turns=t,
                                      conclude_prompt=self._explore_conclude_prompt(intent, session))
            except Exception as exc:
                LOG.warning("[%s] explore %s 异常: %s", self.code, intent["id"], exc)
                return {"intent": intent, "desc": f"worker 异常: {exc}", "flags": [], "success": False}
            if not isinstance(res, dict):
                return {"intent": intent, "desc": "worker 非 SessionWorker 结果",
                        "flags": [], "success": False}
            self._scan_session_result(res, session)
            text = res.get("raw", "") or ""
            note_path = self.ws / f"step_{intent['id']}.md"
            try:
                note_path.write_text(f"# {intent['id']} {intent.get('action', '')}\n\n{text[:3000]}\n")
            except OSError:
                note_path = None
            LOG.info("[%s] explore %s 输出: %s", self.code, intent["id"],
                     text[:400].replace("\n", " "))
            if res["accepted"] and res["kind"] == "fact":
                desc = res["data"]
                if note_path:
                    desc += f"（详见 {note_path.name}）"
                return {"intent": intent, "desc": desc, "flags": [], "success": True}
            reason = (res.get("error") or "探索无有效产出")[:300]
            return {"intent": intent, "desc": reason, "flags": [], "success": False}

        # ---- api 直连兜底：优先级决定深度（high 深挖、normal 中、low 快）----
        # ⚠️ 2026-08-13 evidence 落盘：让 _scan_session_result / cairn _drain_flags
        # 扫到 flag（agentic 模式默认 output 只在内存里）
        ev_dir = self.ws / "evidence" / "api"
        r = self.llm.agentic("", self._explore_prompt(intent, "api"), max_turns=t, evidence_dir=ev_dir)
        self._scan_agentic_result(r)
        text = r.get("text", "")
        # 写步骤笔记文件
        note_path = self.ws / f"step_{intent['id']}.md"
        try:
            note_path.write_text(f"# {intent['id']} {intent.get('action', '')}\n\n{text[:3000]}\n")
        except OSError:
            note_path = None
        LOG.info("[%s] explore %s 输出: %s", self.code, intent["id"],
                 text[:400].replace("\n", " "))
        # ⚠️ 2026-08-13 移除 LLM 文本 grep flag：之前 deepseek-v4-flash 在推理文本里
        # 编 UUID flag{2a51614f-...}，通过 is_plausible_flag 校验（UUID 是合法格式），
        # 被 _report_flags 写进 flags_found.jsonl → cairn 30s 同步 → 平台拒收。
        # 现在 flag 由 _scan_agentic_result 接管（只信 command output，已写到
        # evidence/<session>/cmd_*.out 真实输出）。不要从 LLM 文本里 grep。
        flags = []
        fact = self.llm.parse_json(text)
        desc = ""
        if isinstance(fact, dict):
            desc = (fact.get("data") or {}).get("description", "")
        if not desc:
            desc = text[:400]
        if note_path:
            desc += f"（详见 {note_path.name}）"
        success = bool(desc) and "该方向失败" not in desc and "走不通" not in desc
        return {"intent": intent, "desc": desc, "flags": flags, "success": success}

    def _explore_intents(self, intents: list[dict]) -> None:
        """并行 explore 最多 N 个 intent（② 题内并行，学 cairn 多 worker）。

        每个 explore 用独立 claude 子进程跑，互不阻塞；完成后统一应用 fact/flag 到图。
        """
        n = min(self.parallel, len(intents))
        results: list[dict] = []
        if n <= 1:
            for it in intents:
                results.append(self._explore_one(it))
        else:
            LOG.info("[%s] 并行 explore %d 个方向", self.code, n)
            with ThreadPoolExecutor(max_workers=n) as ex:
                futs = [ex.submit(self._explore_one, it) for it in intents]
                for f in futs:
                    try:
                        results.append(f.result())
                    except Exception as exc:
                        LOG.warning("[%s] explore 线程异常: %s", self.code, exc)
        # 统一应用（主线程顺序写，避免并发写冲突）
        for r in results:
            for flag in r["flags"]:
                self._report_flags(flag)
            it = r["intent"]
            if r["success"]:
                f = self.graph.add_fact(r["desc"], it["id"])
                self.graph.conclude_intent(it["id"], f["id"])
                LOG.info("[%s] fact %s: %s", self.code, f["id"], r["desc"][:120])
            else:
                reason = (r["desc"] or "探索无有效产出").replace("该方向失败：", "").replace("（详见", "(")
                self.graph.drop_intent(it["id"], reason[:300])
                LOG.info("[%s] %s 方向丢弃: %s", self.code, it["id"], reason[:80])
        self.graph.set_flag_progress(self.flags_found)
        self.graph.save()
