"""Scheduler 人工控制：暂停/恢复/优先级（从 control.json 读）。

从原 scheduler.py 抽出的方法：
  _is_paused, _control_priority, _apply_controls, _select_targets
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

LOG = logging.getLogger("scheduler.control")


class ControlMixin:
    """人工控制 mixin：被 Scheduler 继承，提供 control.json 读写 + 任务排序。

    依赖 Scheduler 上的属性：
      self.workspace, self._paused, self._closed, self._skip_start,
      self.store
    """
    workspace: Path
    _paused: set
    _closed: set
    _skip_start: set
    store: object  # StatusStore

    def _is_paused(self, code: str) -> bool:
        try:
            ctl = json.loads((self.workspace / code / "control.json").read_text(encoding="utf-8"))
            return bool(ctl.get("paused", False))
        except Exception:
            return False

    def _control_priority(self, code: str) -> int:
        try:
            ctl = json.loads((self.workspace / code / "control.json").read_text(encoding="utf-8"))
            return int(ctl.get("priority", 0) or 0)
        except Exception:
            return 0

    def _apply_controls(self) -> None:
        """每轮读取 control.json：暂停的活跃题 kill+close；恢复的题移出暂停集并可重新入队。"""
        # 已暂停但被恢复 → 移出（并从 _closed 里捞回，允许重新入队）
        for code in list(self._paused):
            if not self._is_paused(code):
                self._paused.discard(code)
                self._closed.discard(code)
        # 活跃但新被暂停 → 关容器
        for code in list(self.procs.keys()):
            if code in self._paused:
                continue
            if self._is_paused(code):
                LOG.info("控制: 暂停活跃题 %s，关容器", code)
                self.store.log_event(f"人工暂停 {code}")
                self._paused.add(code)
                self._close(code)   # _close 内 kill + close_challenge + 幂等

    def _select_targets(self, challenges: list) -> list:
        """返回未完成、未关闭、未跳过、未暂停的题；按人工优先级降序。"""
        todo = [c for c in challenges
                if not c.is_completed and c.unique_code not in self._closed]
        if self._skip_start:
            todo = [c for c in todo if c.unique_code not in self._skip_start]
        # 排除已暂停（含控制文件里暂停但从未启动的）
        todo = [c for c in todo
                if c.unique_code not in self._paused and not self._is_paused(c.unique_code)]
        # 第一轮：待重试的题等第二轮再试（第二轮 _retry_queue 已清空）
        if not self._pass2:
            todo = [c for c in todo if c.unique_code not in self._retry_queue]
        todo.sort(key=lambda c: -self._control_priority(c.unique_code))
        return todo
