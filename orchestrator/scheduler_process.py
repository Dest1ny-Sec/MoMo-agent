"""Scheduler 子进程管理：spawn solver 子进程 / 杀死 / reap。

从原 scheduler.py 抽出的方法：
  _safe_list, _tick_collect_active, _refresh_pending, _fill_slots,
  _spawn_solver, _on_start_fail, _kill_challenge, _stop_all, _on_solver_exit

依赖 Scheduler 上的属性：
  self.procs, self._spawn_ts, self._closed, self._skip_start,
  self._start_fail_count, self._start_fail_limit, self.workspace,
  self.adapter, self.store, self.max_active
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from luvvv_common import ROOT

LOG = logging.getLogger("scheduler.process")


class ProcessMixin:
    """子进程 mixin：solver 子进程全生命周期。"""
    procs: dict
    _spawn_ts: dict
    _closed: set
    _skip_start: set
    _start_fail_count: dict
    _start_fail_limit: int
    workspace: Path
    adapter: object
    store: object
    max_active: int

    def _safe_list(self) -> list | None:
        """拉题（带容错）。失败返回 None 表示"瞬时网络问题"，不要据此判结束。"""
        try:
            challenges = self.adapter.list_challenges()
            if getattr(self, "challenge_filter", ""):
                import re as _re
                pat = _re.compile(self.challenge_filter)
                challenges = [c for c in challenges if pat.search(c.unique_code)]
            return challenges
        except Exception as exc:
            LOG.warning("list_challenges 失败: %s", exc)
            return None

    def _tick_collect_active(self) -> tuple[set, list]:
        """一轮开始：扫描子进程状态，区分仍在跑 vs 已退出。"""
        active: set = set()
        reaped: list = []
        for code, p in self.procs.items():
            if p.poll() is None:
                active.add(code)
            else:
                reaped.append(code)
        return active, reaped

    def _refresh_pending(self, pending: list) -> list:
        """根据平台最新题目状态重算 pending 队列。"""
        fresh = self._safe_list()
        if fresh is None:
            # 拉题失败：保持 pending 不变，等下轮重试
            return pending
        if not fresh:
            return []
        in_flight = set(self.procs.keys())
        remaining = [
            c for c in fresh
            if not c.is_completed and c.unique_code not in in_flight
            and c.unique_code not in self._skip_start
        ]
        return self._select_targets(remaining)

    def _fill_slots(self, pending: list, active: set) -> list:
        """补位：起新 solver 填满到 max_active。"""
        while len(active) < self.max_active and pending:
            ch = pending[0]
            code = ch.unique_code
            if self._spawn_solver(ch):
                active.add(code)
                pending.pop(0)
            else:
                pending.pop(0)
                pending.append(ch)
                time.sleep(3)
                break
        return pending

    # ---------- 启动 solver ----------
    def _spawn_solver(self, ch) -> bool:
        code = ch.unique_code
        if code in self._closed or code in self._skip_start:
            return False  # 已关闭/已跳过：不重跑（防死循环重跑）
        ws = self.workspace / code
        ws.mkdir(parents=True, exist_ok=True)
        # 平台 stopped→available 状态切换有 race condition，短暂 invalid_state
        # 是正常现象（容器在拉起中）。重试 start 5 次 + 中间 list 拿真实地址。
        addrs: list[str] = []
        for attempt in range(5):
            try:
                addrs = self.adapter.start_challenge(code) or []
            except Exception as exc:
                LOG.warning("start %s 第%d次失败: %s", code, attempt + 1, exc)
                addrs = []
            if not addrs:
                # 重新 list 拿真实状态
                refreshed = self._safe_list() or []
                for c in refreshed:
                    if c.unique_code == code:
                        addrs = c.container_addrs
                        if addrs:
                            LOG.info("start %s 第%d次: list 拿到地址 %s", code, attempt + 1, addrs)
                            break
            if addrs:
                break
            time.sleep(2)  # 等平台容器拉起
        if not addrs:
            LOG.warning("start %s 5 次后仍无地址，标记为跳过", code)
            self.store.log_event(f"start {code} 5 次失败，本轮跳过")
            self._start_fail_count[code] = self._start_fail_limit  # 强制 skip
            self._on_start_fail(code)
            return False
        self._start_fail_count[code] = 0

        mission = {
            "unique_code": code,
            "title": ch.title[:100],
            "description": ch.description,
            "flag_count": ch.flag_count,
            "container_addr": addrs[0] if addrs else "",
            "difficulty": ch.difficulty,
            "total_score": ch.total_score,
            "platform": self.adapter.name,
        }
        (ws / "mission.json").write_text(json.dumps(mission, ensure_ascii=False), encoding="utf-8")
        st = self.store.challenge(code)
        st.update(status="solving", container_addr=addrs, started_at=time.strftime("%H:%M:%S"))
        self.store.log_event(f"启动题目 {code} addr={addrs}")

        # ⚠️ 关键：solver 子进程剥离提交凭证（BENCHMARK_* / TSEC_*）。
        # 否则模型（claude/agentic）会拿 token 直接 curl 提交 flag，绕过 scheduler 计分去重
        # （导致总分漏计 + 平台配额被模型乱提交耗光）。提交只由 orchestrator 做。
        import os as _os
        solver_env = {k: v for k, v in _os.environ.items()
                      if not k.startswith("BENCHMARK_") and not k.startswith("TSEC_")}
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "solver.loop", "--code", code,
             "--workspace", str(self.workspace)],
            cwd=str(ROOT),
            env=solver_env,
            stdout=open(ws / "solver.log", "a", buffering=1), stderr=subprocess.STDOUT,
        )
        self.procs[code] = proc
        self._spawn_ts[code] = time.time()
        return True

    def _on_start_fail(self, code: str) -> None:
        """start 连续失败 → 跳过 + 尝试 close 重置平台状态（防死循环卡队列）。
        关键：max_active=3 满时不算"失败"，是临时状态，下轮重试。
        只有 close 也失败（容器被前一个 client 锁）才永久 skip。
        ⚠️ 2026-08-13：累计 2 次 _on_start_fail 触发（不是单轮 5 次）就永久 skip。
        之前 c-03 容器锁住后单轮 5 次重试完 → _start_fail_count 重置为 0 → 下轮再来 5 次
        死循环卡住，浪费大量 retry token。
        """
        self._start_fail_count[code] = self._start_fail_count.get(code, 0) + 1
        # 始终先 close 重置
        try:
            self.adapter.close_challenge(code)
        except Exception as exc:
            # close 失败 = 容器被锁（不属于我们），永久 skip
            self._skip_start.add(code)
            self.store.log_event(f"start {code} + close {code} 都失败（容器被锁？），永久跳过")
            LOG.warning("start+close %s 都失败，永久 skip", code)
            return
        if self._start_fail_count[code] >= 2:  # 改 2：累计 2 轮重试就永久 skip
            self._skip_start.add(code)
            self.store.log_event(f"start {code} 累计 {self._start_fail_count[code]} 轮失败，永久 skip")
            LOG.warning("start %s 累计 %d 轮失败，永久 skip", code, self._start_fail_count[code])
        elif self._start_fail_count[code] >= self._start_fail_limit:
            # 5 次都 invalid_state（很可能是 max_active 满），不永久 skip，让下轮重试
            self._start_fail_count[code] = 0  # 重置计数，让下轮有 5 次重试预算
            self.store.log_event(f"start {code} 连续 {self._start_fail_limit} 次 invalid_state（max_active?），下轮重试")
            LOG.warning("start %s 5 次 invalid_state，不 skip（max_active=3 满），下轮重试", code)

    def _kill_challenge(self, code: str) -> None:
        p = self.procs.get(code)
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
            try:
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def _stop_all(self) -> None:
        for code in list(self.procs.keys()):
            self._kill_challenge(code)
        # 兜底：关掉所有已启动未关闭的容器
        for code in list(self.procs.keys()):
            try:
                self.adapter.close_challenge(code)
            except Exception:
                pass

    def _on_solver_exit(self, code: str) -> None:
        """solver 自然退出：补提交 flag + 打日志 + 关闭容器。"""
        self._drain_flags(code)
        st = self.store.challenge(code)
        # 打 solver 日志尾部（诊断用）：能看到 bootstrap/Reason/报错
        slog = self.workspace / code / "solver.log"
        if slog.exists():
            try:
                lines = [l for l in slog.read_text(encoding="utf-8", errors="replace")
                         .splitlines() if l.strip()]
                for l in lines[-12:]:
                    LOG.info("[solver:%s] %s", code, l[:300])
            except OSError:
                pass
        if st.get("is_completed"):
            self._close(code)
            return
        # solver 退出且未通关：关容器腾槽。第一轮 → 进重试队列；第二轮 → 永久关闭
        if self._pass2:
            LOG.info("solver %s 退出（第二轮未通关），永久关闭", code)
            self.store.log_event(f"solver {code} 第二轮未通关，关闭")
            self._close(code)
        else:
            LOG.info("solver %s 退出（未通关），关容器进重试队列", code)
            self.store.log_event(f"solver {code} 退出，待重试")
            self._retry_close(code)

    def _retry_close(self, code: str) -> None:
        """未通关关容器但保留重试资格：加入 attempted + retry_queue，不永久 _closed。
        进度保留在 workspace/<code>/graph.json，第二轮用同一 workspace 继续。"""
        self._attempted.add(code)
        self._retry_queue.add(code)
        st = self.store.challenge(code)
        try:
            self.adapter.close_challenge(code)
            st["container_status"] = "stopped"
            self.store.log_event(f"题目 {code} 待重试（关闭容器，进度已保存）")
            LOG.info("题目 %s 未解出，关容器进重试队列（第%d轮）", code, 2 if self._pass2 else 1)
        except Exception as exc:
            LOG.warning("close %s 失败: %s", code, exc)
        self._kill_challenge(code)
        self.procs.pop(code, None)
