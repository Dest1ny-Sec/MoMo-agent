"""Scheduler 回收：硬超时 + 进度式回收（无进展超时则提前关题换）。

从原 scheduler.py 抽出的方法：
  _check_hard_timeout, _line_count, _progress_token, _reclaim_grace_for, _check_progress_reclaim
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

LOG = logging.getLogger("scheduler.reclaim")


class ReclaimMixin:
    """回收 mixin：硬超时 + 进度式回收。"""
    workspace: Path
    procs: dict
    _spawn_ts: dict
    _last_token: dict
    _stall_since: dict
    hard_timeout_sec: float
    reclaim_min_wall: float
    reclaim_grace: float
    store: object
    _close: callable  # Scheduler._close

    # ---------- 硬超时 ----------
    def _check_hard_timeout(self, code: str) -> None:
        if code not in self.procs:
            return
        elapsed = time.time() - self._spawn_ts.get(code, time.time())
        if self.hard_timeout_sec > 0 and elapsed > self.hard_timeout_sec:
            LOG.warning("solver %s 硬超时（%.0fs），强制结束", code, elapsed)
            self.store.log_event(f"solver {code} 硬超时回收")
            self._kill_challenge(code)

    _kill_challenge: callable  # ProcessMixin 提供

    # ---------- 进度式回收 ----------
    @staticmethod
    def _line_count(p: Path) -> int:
        try:
            return sum(1 for _ in open(p, "r", errors="replace"))
        except OSError:
            return 0

    def _progress_token(self, code: str) -> tuple:
        """进展指纹：只统计单调量（flags_found/submission 行数 + graph facts 数）。

        不把 graph.json mtime 当进展——loop 每轮都 save，mtime 恒变，会把死循环
        误判为有进展。三字段任一变化 → 重置停摆计时。
        """
        ws = self.workspace / code
        flags = self._line_count(ws / "flags_found.jsonl")
        subs = self._line_count(ws / "submission_results.jsonl")
        facts = 0
        gp = ws / "graph.json"
        if gp.exists():
            try:
                facts = len(json.loads(gp.read_text(encoding="utf-8")).get("facts", {}))
            except Exception:
                pass
        return (flags, subs, facts)

    def _reclaim_grace_for(self, code: str) -> float:
        st = self.store.challenge(code)
        grace = self.reclaim_grace
        if st.get("correct_flag_count", 0) > 0:
            grace *= 2.0                     # 已拿 flag → 多阶段，给双倍
        if int(st.get("level", 0) or 0) >= 4:
            grace *= 1.5                     # hard 题放宽
        return grace

    def _check_progress_reclaim(self, code: str) -> None:
        if code not in self.procs:
            return
        tok = self._progress_token(code)
        if tok != self._last_token.get(code):
            self._last_token[code] = tok
            self._stall_since[code] = time.time()
            return
        wall = time.time() - self._spawn_ts.get(code, time.time())
        stalled = time.time() - self._stall_since.get(code, time.time())
        if wall >= self.reclaim_min_wall and stalled >= self._reclaim_grace_for(code):
            LOG.warning("solver %s 无进展 %.0fs（wall=%.0fs），提前回收换题", code, stalled, wall)
            self.store.log_event(f"solver %s 无进展回收（%ds 无新 fact/flag）" % (code, int(stalled)))
            if self._pass2:
                self._close(code)
            else:
                self._retry_close(code)     # 第一轮：进重试队列，不永久关
