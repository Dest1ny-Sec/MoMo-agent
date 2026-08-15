"""Scheduler 主类：编排器核心调度循环。

文件拆分（拆 526 行 scheduler.py 为 5 个模块）：
  scheduler.py            - 本文件：主类、生命周期、run/finish 入口
  scheduler_control.py    - 人工控制（暂停/恢复/优先级）
  scheduler_process.py    - 子进程生命周期（spawn/kill/reap）
  scheduler_reclaim.py    - 硬超时 + 进度式回收
  scheduler_submit.py     - 提交循环（drain/submit/dedupe）

行为完全等价：拆分前/后跑同一道题，flags_found.jsonl 行为一致。
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from luvvv_common import ROOT
from orchestrator.metrics import Metrics
from orchestrator.scheduler_control import ControlMixin
from orchestrator.scheduler_process import ProcessMixin
from orchestrator.scheduler_reclaim import ReclaimMixin
from orchestrator.scheduler_submit import SubmitMixin
from orchestrator.status import StatusStore
from adapters.base import Challenge, PlatformAdapter

LOG = logging.getLogger("scheduler")


class Scheduler(ControlMixin, ProcessMixin, ReclaimMixin, SubmitMixin):
    """3-slot 调度器：拉题 → 起 solver 子进程 → 提交 flag → 通关/退出时关容器。

    编排器唯一接触计分 API（via PlatformAdapter）；solver 子进程只写文件、绝不碰 API。
    """
    def __init__(self, cfg: dict, adapter: PlatformAdapter, store: StatusStore, metrics: Metrics):
        self.cfg = cfg
        self.adapter = adapter
        self.store = store
        self.metrics = metrics
        self.max_active = int(cfg["scheduler"]["max_active"])
        self.workspace = ROOT / "workspace"
        # 题目过滤（正则，匹配 unique_code）：只跑指定前缀，如 "^b-" 只跑 b 家族
        self.challenge_filter = cfg["scheduler"].get("challenge_filter", "") or ""
        # 硬超时（统一，分钟）：solver 子进程整体超时回收，防极端卡死
        self.hard_timeout_sec = float(cfg["scheduler"].get("hard_timeout_min", 20) or 20) * 60
        # 进度式回收：进展 token 连续 grace 未变 + 存活过 min_wall → 提前关容器换题
        self.reclaim_min_wall = float(cfg["scheduler"].get("progress_min_wall_min", 5) or 5) * 60
        self.reclaim_grace = float(cfg["scheduler"].get("progress_grace_min", 12) or 12) * 60
        # 子进程 / 状态
        self.procs: dict[str, "subprocess.Popen"] = {}  # type: ignore[name-defined]
        self._spawn_ts: dict[str, float] = {}
        # 进度式回收 token 追踪（ReclaimMixin 用）
        self._last_token: dict[str, tuple] = {}
        self._stall_since: dict[str, float] = {}
        # 人工控制
        self._paused: set[str] = set()
        # 两轮制：尝试过的题 + 待重试队列 + 是否已进入第二轮（第一轮没做出来的，全部试完后重试）
        self._attempted: set[str] = set()
        self._retry_queue: set[str] = set()
        self._pass2 = False
        # 平台 cfc 追踪（_sync_platform_cfc 用；scheduler 自己提交成功后同步，防误判 solver 自提交）
        self._seen_cfc: dict[str, int] = {}
        # 提交 / 关闭
        self._submitted: dict[str, set[str]] = {}
        self._seen_flag_files: dict[str, int] = {}
        self._closed: set[str] = set()
        self._task_ended = False
        # start 失败保护
        self._start_fail_count: dict[str, int] = {}
        self._skip_start: set[str] = set()
        self._start_fail_limit = 3
        # 错误提交上限：每题最多提交 N 个错误 flag 就停止（防 AI 瞎猜刷屏）
        self._wrong_sub_count: dict[str, int] = {}
        self._max_wrong_sub = int(cfg["scheduler"].get("max_wrong_submissions", 12) or 12)

    # ---------- 主入口 ----------
    def run(self) -> dict:
        self.store.update(phase="running",
                          started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                          platform=self.adapter.name)
        LOG.info("=== 开始跑分 (adapter=%s) ===", self.adapter.name)
        try:
            challenges = self._fetch_challenges()
            if challenges is None:
                return self._finish("error")
            self._init_status(challenges)
            pending = self._select_targets(challenges)
            for ch in challenges:
                if ch.is_completed:
                    self._submitted.setdefault(ch.unique_code, set()).add("*completed*")
            LOG.info("待解题目: %s", [c.unique_code for c in pending])
            self.store.log_event(f"获取题目 {len(pending)} 道")

            while True:
                self._apply_controls()   # 人工暂停/恢复（读 control.json）

                active, reaped = self._tick_collect_active()
                for code in list(active):
                    self._drain_flags(code)
                    self._check_hard_timeout(code)
                    self._check_progress_reclaim(code)
                for code in reaped:
                    self._on_solver_exit(code)

                pending = self._refresh_pending(pending)
                # 补位
                self._fill_slots(pending, active)

                # 两轮制：所有题都尝试过一遍（无活跃、无未试的 pending、有待重试的）→ 第二轮
                if not active and not pending and self._retry_queue:
                    LOG.info("=== 第二轮：重试 %d 道未解题 ===", len(self._retry_queue))
                    self._pass2 = True
                    fresh = self._safe_list() or []
                    pending = [c for c in fresh if c.unique_code in self._retry_queue]
                    self._retry_queue = set()
                    self._attempted = set()
                    self._fill_slots(pending, active)   # 立即补位第二轮

                if not self._has_more(active, pending):
                    break
                if self._task_ended or self.store.get("task_ended"):
                    LOG.warning("任务已结束（平台侧）")
                    break
                time.sleep(2)

            return self._finish("finished")
        except KeyboardInterrupt:
            raise
        except Exception:
            LOG.exception("主循环异常")
            raise
        finally:
            LOG.info("清理 solver 子进程...")
            self._stop_all()

    def _has_more(self, active: set[str], pending: list) -> bool:
        """是否还有题要处理（没活跃 && 没 pending && 没待重试 才结束）。"""
        return bool(active) or bool(pending) or bool(self._retry_queue)

    # ---------- 题目列表 ----------
    def _fetch_challenges(self) -> list[Challenge] | None:
        try:
            challenges = self.adapter.list_challenges()
            if self.challenge_filter:
                import re as _re
                pat = _re.compile(self.challenge_filter)
                challenges = [c for c in challenges if pat.search(c.unique_code)]
            return challenges
        except Exception as exc:
            category = self.adapter.classify(exc)
            LOG.error("获取题目失败 [%s]: %s", category, exc)
            self.store.update(phase="error")
            self.store.log_event(f"获取题目失败: {exc}")
            if category == "invalid_state":
                self._task_ended = True
                self.store.update(task_ended=True)
            return None

    def _init_status(self, challenges: list[Challenge]) -> None:
        self.store.update(total_challenges=len(challenges))
        for ch in challenges:
            st = self.store.challenge(ch.unique_code)
            st.update(title=ch.title[:80], difficulty=ch.difficulty, level=ch.level,
                      total_score=ch.total_score, flag_count=ch.flag_count,
                      correct_flag_count=ch.correct_flag_count, is_completed=ch.is_completed,
                      container_status=ch.container_status, container_addr=ch.container_addrs)
            if ch.is_completed:
                st["status"] = "completed"

    # ---------- 关闭（仍留这里，因为只跟主类交互） ----------
    def _close(self, code: str) -> None:
        if code in self._closed:
            return
        self._closed.add(code)
        st = self.store.challenge(code)
        try:
            self.adapter.close_challenge(code)
            st["container_status"] = "stopped"
            self.store.log_event(f"关闭题目 {code}")
            LOG.info("关闭题目 %s", code)
        except Exception as exc:
            LOG.warning("close %s 失败: %s", code, exc)
        self.metrics.log_challenge_result({
            "unique_code": code, "title": st.get("title", code),
            "difficulty": st.get("difficulty", ""), "status": st.get("status", ""),
            "flag_count": st.get("flag_count", 0), "correct_flags": st.get("correct_flag_count", 0),
            "score": st.get("cumulative_score", 0), "first_flag_sec": st.get("first_flag_sec"),
            "solver_iterations": 0, "hints_used": 0,
        })
        self._kill_challenge(code)
        self.procs.pop(code, None)
        self._closed.add(code)

    def _completed_count(self) -> int:
        return sum(1 for st in self.store.snapshot()["challenges"].values()
                   if st.get("is_completed"))

    # ---------- 结束 ----------
    def _finish(self, phase: str) -> dict:
        snap = self.store.snapshot()
        self.store.update(phase=phase)
        LOG.info("=== 跑分结束 phase=%s 通关=%s/%s 总分=%s ===",
                 phase, snap["completed_challenges"], snap["total_challenges"], snap["total_score"])
        return {"phase": phase, "platform": self.adapter.name,
                "completed": snap["completed_challenges"], "total": snap["total_challenges"],
                "score": snap["total_score"]}
