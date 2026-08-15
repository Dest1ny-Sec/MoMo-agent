"""图黑板：facts / intents / goal —— cairn 式状态空间搜索的核心数据结构。

设计（对照 cairn-ref）：
- 所有发现都是 fact（客观、带证据的结论）
- 所有探索方向都是 intent（从若干 fact 出发，走向一个新 fact）
- 图从 origin 经由 intent 产出新 fact，最终通向 goal（拿全 flag）
- 持久化为 JSON（跨轮次/跨回填不丢），供 Reason 每次读全图规划

仅依赖 stdlib，不引入第三方。
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

LOG = logging.getLogger("solver.graph")


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _counter_from_ids(ids: list[str], prefix: str) -> int:
    n = 0
    for i in ids:
        m = re.match(rf"^{prefix}(\d+)$", i)
        if m:
            n = max(n, int(m.group(1)))
    return n


class Graph:
    """一题的完整黑板。所有读写都过这里，确保持久化与快照一致。"""

    def __init__(self, mission: dict, ws: Path):
        self.mission = mission
        self.ws = Path(ws)
        self.path = self.ws / "graph.json"
        self._facts: dict[str, dict] = {}
        self._intents: list[dict] = []
        self._hints: list[dict] = []
        # flag 进度（⑥：图里能看到拿了几个 flag）
        self._flags_found: set[str] = set()
        self._load_or_init()

    # ---------- 持久化 ----------
    def _load_or_init(self) -> None:
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                self._facts = d.get("facts", {})
                self._intents = d.get("intents", [])
                self._hints = d.get("hints", [])
                # ⚠️ 2026-08-13 过滤脏 flags_found：之前 f2-06 graph.json 留了
                # 历史假 flag `FLAG{` @0、`}`（旧版本 bootstrap 瞎猜乱码）→
                # reason LLM 看到 flag_progress=1/1 误判 complete → solver 提前退出。
                # 内联过滤（不能用 is_plausible_flag 避免循环 import）：
                # 只保留 alphanumeric + {} + -_ 内容的 flag（合法格式）
                import re as _re
                _PL = _re.compile(r"^[Ff][Ll][Aa][Gg]\{[A-Za-z0-9_\-]{4,200}\}$")
                raw_flags = d.get("flags_found", [])
                self._flags_found = {f for f in raw_flags if isinstance(f, str) and _PL.match(f)}
                if len(raw_flags) != len(self._flags_found):
                    LOG.warning("[%s] graph.json flags_found 过滤掉 %d 个脏 flag（乱码/瞎猜）",
                                self.mission.get("unique_code", "?"),
                                len(raw_flags) - len(self._flags_found))
                self._fact_counter = _counter_from_ids(list(self._facts), "f")
                self._intent_counter = _counter_from_ids(
                    [it.get("id", "") for it in self._intents], "i")
                return
            except Exception:
                pass
        addr = self.mission.get("container_addr") or "(待获取)"
        desc = self.mission.get("description") or self.mission.get("title") or self.mission.get("unique_code", "")
        flag_count = self.mission.get("flag_count") or "?"
        self._fact_counter = 0
        self._intent_counter = 0
        self._facts["origin"] = {
            "id": "origin",
            "title": "题目信息",
            "content": f"TARGET: {addr}\n任务: {desc}",
            "producedBy": None,
            "createdAt": utcnow(),
        }
        self._facts["goal"] = {
            "id": "goal",
            "title": "目标",
            "content": f"拿到全部 {flag_count} 个 flag 并提交成功",
            "producedBy": None,
            "createdAt": utcnow(),
        }
        self.save()

    def save(self) -> None:
        d = {"facts": self._facts, "intents": self._intents,
             "hints": self._hints, "mission": self.mission,
             "flags_found": sorted(self._flags_found)}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def set_flag_progress(self, flags_found: set[str]) -> None:
        """更新已找到的 flag 集合（⑥ flag 进度，让 Reason 看到还差几个）。"""
        self._flags_found = set(flags_found)

    # ---------- facts ----------
    @property
    def facts(self) -> list[dict]:
        return list(self._facts.values())

    def get_fact(self, fid: str) -> dict | None:
        return self._facts.get(fid)

    def add_fact(self, content: str, produced_by: str | None = None) -> dict:
        self._fact_counter += 1
        fid = f"f{self._fact_counter:03d}"
        fact = {"id": fid, "title": f"发现 {fid}", "content": content,
                "producedBy": produced_by, "createdAt": utcnow()}
        self._facts[fid] = fact
        return fact

    # ---------- intents ----------
    @property
    def intents(self) -> list[dict]:
        return list(self._intents)

    def open_intents(self) -> list[dict]:
        return [it for it in self._intents if it.get("state") == "open"]

    def add_intent(self, description: str, from_facts: list[str],
                   priority: str = "normal") -> dict:
        self._intent_counter += 1
        iid = f"i{self._intent_counter:03d}"
        intent = {
            "id": iid, "action": description, "from": list(from_facts),
            "state": "open", "to": None, "reason": "", "priority": priority,
            "createdAt": utcnow(), "concludedAt": None,
        }
        self._intents.append(intent)
        return intent

    def get_intent(self, iid: str) -> dict | None:
        for it in self._intents:
            if it["id"] == iid:
                return it
        return None

    def conclude_intent(self, iid: str, fact_id: str | None) -> None:
        for it in self._intents:
            if it["id"] == iid:
                it["state"] = "done"
                it["to"] = fact_id
                it["concludedAt"] = utcnow()

    def drop_intent(self, iid: str, reason: str) -> None:
        for it in self._intents:
            if it["id"] == iid:
                it["state"] = "dropped"
                it["reason"] = reason
                it["concludedAt"] = utcnow()

    # ---------- hints ----------
    @property
    def hints(self) -> list[dict]:
        return list(self._hints)

    def set_hint(self, content: str) -> None:
        self._hints.append({"id": f"h{len(self._hints)+1}", "content": content,
                            "createdAt": utcnow()})

    # ---------- 图快照（喂给 Reason 读全图） ----------
    def snapshot(self) -> str:
        """把图渲染成紧凑 JSON 字符串，供 Reason prompt 使用。"""
        facts = [{"id": f["id"], "content": f["content"][:800]} for f in self.facts]
        intents = [
            {"id": it["id"], "action": it["action"], "from": it.get("from", []),
             "state": it.get("state"), "to": it.get("to"),
             "reason": it.get("reason", "")[:200]}
            for it in self._intents
        ]
        goal = self._facts.get("goal", {}).get("content", "")
        hints = [h["content"] for h in self._hints]
        total_flags = int(self.mission.get("flag_count", 0) or 0)
        return json.dumps({
            "facts": facts, "intents": intents, "goal": goal, "hints": hints,
            "flag_progress": f"{len(self._flags_found)}/{total_flags} 已找到",
        }, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"<Graph facts={len(self._facts)} intents={len(self._intents)}>"
