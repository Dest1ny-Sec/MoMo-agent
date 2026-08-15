"""SolverLoop 主类：cairn 式图搜索主循环（每题一个子进程）。

文件拆分（拆 494 行 loop.py 为 5 个模块）：
  loop.py                - 本文件：主类 GraphSolver、run() 主循环、flag 通道、scan
  loop_prompts.py        - 所有 prompt 构造 + load_prompt + FLAG_RE/is_plausible_flag
  loop_bootstrap.py      - bootstrap 阶段（直接尝试）
  loop_reason.py         - reason 阶段（读图规划方向）+ 兜底 fallback
  loop_explore.py        - explore 阶段（并行执行 intent）

cairn 流程：bootstrap（直接尝试）→ reason（读图规划方向）→ explore（逐条执行写回 facts）
→ 再 reason → ... 直到目标达成 / 自判穷尽 / 超轮次。
flag 通道：发现疑似 flag 写入 workspace/<code>/flags_found.jsonl，由调度器统一提交。
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from luvvv_common import ROOT, configure_logging, load_config
from solver.graph import Graph
from solver.llm import LLMClient
from solver.loop_prompts import (
    FLAG_RE,
    is_plausible_flag,
    PromptMixin,
)
from solver.loop_bootstrap import BootstrapMixin
from solver.loop_reason import ReasonMixin
from solver.loop_explore import ExploreMixin

LOG = logging.getLogger("solver.loop")


class GraphSolver(PromptMixin, BootstrapMixin, ReasonMixin, ExploreMixin):
    """cairn 图搜索求解器：bootstrap → reason → explore 循环。"""
    def __init__(self, cfg: dict, mission: dict, ws: Path):
        self.cfg = cfg
        self.mission = mission
        self.ws = Path(ws)
        self.code = mission["unique_code"]
        self.graph = Graph(mission, self.ws)
        self.llm = LLMClient(cfg)
        scfg = cfg.get("solver", {})
        self.max_rounds = int(scfg.get("max_rounds", 50))
        self.explore_max_turns = int(scfg.get("explore_max_turns", 50))
        # 最低轮数：不到此轮数时 Reason 返回 noop 不能放弃，强制继续深入已有线索（防过早 give up）
        self.min_rounds = int(scfg.get("min_rounds_before_giveup", 6) or 6)
        self.flags_found: set[str] = self._load_submitted()
        # Worker：claude（SessionWorker，cairn 式 session+conclude）；无 worker 时 api 直连兜底
        from solver.worker import build_worker
        self.worker_type = scfg.get("worker", "claude")
        self.worker = build_worker(cfg)
        self.parallel = int(scfg.get("explore_parallel", 3) or 1)
        self.reason_max_intents = int(scfg.get("reason_max_intents", 5) or 5)

    def _load_submitted(self) -> set[str]:
        """从 submission_results.jsonl 加载已提交过的 flag（不重复提交）。

        ⚠️ 2026-08-13 加 is_plausible_flag 过滤：之前 f2-06 graph.json flags_found
        留了历史假 flag `FLAG{` @0、`}`（旧版本 bootstrap 瞎猜乱码）→ reason LLM
        看到 flag_progress=1/1 误判 complete → solver 提前退出。脏数据需要过滤掉。
        """
        p = self.ws / "submission_results.jsonl"
        if p.exists():
            try:
                return {json.loads(l)["flag"] for l in p.read_text().splitlines()
                        if l.strip() and is_plausible_flag(json.loads(l)["flag"])}
            except Exception:
                pass
        return set()

    # ---------- flag 通道 ----------
    def _flag_in_evidence(self, flag: str) -> bool:
        """Evidence 校验（solver 端）：flag 必须出现在 evidence/**/*.out 里。

        防止 LLM 文本里编的 UUID 格式瞎猜被误写进 flags_found.jsonl。真实 flag
        必然先出现在 evidence/<session>/cmd_*.out 的真实命令输出里。
        """
        ev_root = self.ws / "evidence"
        if not ev_root.exists():
            return False
        try:
            for p in ev_root.rglob("*.out"):
                if not p.is_file():
                    continue
                try:
                    text = p.read_text(errors="replace")
                except OSError:
                    continue
                if flag in text:
                    return True
        except OSError:
            return False
        return False

    def _report_flags(self, text: str | None) -> None:
        for m in FLAG_RE.finditer(text or ""):
            flag = m.group(0)
            if not is_plausible_flag(flag):
                continue
            if flag in self.flags_found:
                continue
            # ⚠️ 2026-08-13 Evidence 校验：防 LLM 文本瞎猜 UUID 写入 flags_found.jsonl
            if not self._flag_in_evidence(flag):
                LOG.warning("[%s] skip flag without evidence（AI 文本瞎猜）: %s", self.code, flag[:60])
                continue
            self.flags_found.add(flag)
            with open(self.ws / "flags_found.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"flag": flag, "ts": time.time()}) + "\n")
            # 立即 touch .notify 让 cairn 实时知道 evidence 已写入
            try:
                (self.ws / "flags.notify").touch()
            except OSError:
                pass
            LOG.info("★ [%s] 发现 flag 候选: %s", self.code, flag[:60])

    def _scan_agentic_result(self, r: dict) -> None:
        """证据优先：只信命令真实输出的 flag；AI 推理文本里的 flag **不主动 grep**（防瞎猜）。

        根治"AI 瞎猜 flag"：编造的 flag 只出现在推理文本里，不会出现在命令输出里。
        之前版本"AI 文本里 grep + evidence 验证"会被二进制乱码触发瞎猜误报。
        """
        # 1) 命令输出 = 真实证据，直接上报
        output_flags: set[str] = set()
        for o in r.get("outputs", []):
            if isinstance(o, dict):
                for m in FLAG_RE.finditer(o.get("output", "") or ""):
                    if is_plausible_flag(m.group(0)):
                        output_flags.add(m.group(0))
        for f in output_flags:
            self._report_flags(f)

    def _scan_session_result(self, res: dict, session: str) -> None:
        """evidence 唯一来源（SessionWorker 路径）：flag 必须出现在 evidence/<session>/*.out
        真实命令输出里，不从 model raw 文本 grep（之前 f2-04/05 把二进制乱码 @0\\u3001
        误报成 flag{乱码} 提交 9 次全被拒）。"""
        text = res.get("raw", "") or ""
        ev_dir = self.ws / "evidence" / session
        ev_flags: set[str] = set()
        if ev_dir.exists():
            for p in ev_dir.iterdir():
                if p.is_file():
                    ev_flags |= set(FLAG_RE.findall(p.read_text(errors="replace")))
        # ❌ 移除：旧版"evidence=0 时退回 model 文本"会引发瞎猜误报
        # ❌ 移除：旧版"model 文本 grep + evidence 验证"会被二进制乱码触发
        for f in ev_flags:
            if is_plausible_flag(f):
                self._report_flags(f)
        # 防御性：如果 model 在 text 里也提到了同样的 flag（一致信号），可加强可信度
        # 但不主动从 text 找新 flag（防止瞎猜）
        for f in ev_flags:
            if f in text and is_plausible_flag(f):
                LOG.debug("[%s] flag %s 在 evidence + model 文本中均出现（增强可信）", self.code, f[:40])

    def _evidence_dir(self, session: str) -> Path:
        d = self.ws / "evidence" / session
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _graph_snapshot(self) -> str:
        return self.graph.snapshot()

    # ---------- 主循环 ----------
    def run(self) -> str:
        try:
            self._bootstrap()
        except Exception as exc:
            LOG.warning("[%s] bootstrap 异常（继续走 reason）: %s", self.code, exc)

        for round_no in range(1, self.max_rounds + 1):
            try:
                decision = self._reason_once()
            except Exception as exc:
                LOG.warning("[%s] Reason 异常，本轮跳过: %s", self.code, exc)
                continue
            if decision == "complete":
                LOG.info("[%s] 目标已达成，结束", self.code)
                return "completed"
            if decision == "noop":
                if round_no < self.min_rounds:
                    # 轮数不足：noop 不能作为放弃理由，强制继续
                    decision = self._fallback_intent(round_no)
                else:
                    LOG.info("[%s] round %d 无新方向（自判穷尽），结束",
                             self.code, round_no)
                    return "exhausted"
            intents = []
            for desc, frm, priority in decision:
                intent = self.graph.add_intent(desc, frm, priority=priority)
                intents.append(intent)
            self.graph.save()
            # 并行 explore（② 题内并行）
            self._explore_intents(intents)
            LOG.info("[%s] round %d 完成（facts=%d）", self.code, round_no, len(self.graph.facts))
        LOG.info("[%s] 达 max_rounds=%d，结束", self.code, self.max_rounds)
        return "exhausted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True)
    parser.add_argument("--workspace", default=str(ROOT / "workspace"))
    args = parser.parse_args()
    configure_logging()
    cfg = load_config()
    ws = Path(args.workspace) / args.code
    mission_path = ws / "mission.json"
    if not mission_path.exists():
        LOG.error("mission.json 不存在: %s", mission_path)
        return
    mission = json.loads(mission_path.read_text(encoding="utf-8"))
    solver = GraphSolver(cfg, mission, ws)
    status = solver.run()
    LOG.info("[%s] solver 结束 status=%s", mission["unique_code"], status)


if __name__ == "__main__":
    main()
