"""内存状态存储：供前端面板轮询读取，贯穿跑分全程。"""
from __future__ import annotations

import threading
import time
from typing import Any


class StatusStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {
            "started_at": None,
            "phase": "idle",            # idle | vpn_check | running | finished | error
            "vpn_ok": None,
            "task_ended": False,
            "total_challenges": 0,
            "completed_challenges": 0,
            "total_score": 0,
            "challenges": {},           # unique_code -> challenge status dict
            "submissions": [],          # 最近提交日志
            "events": [],               # 最近事件日志
            "metrics": {
                "total_flags": 0,
                "correct_flags": 0,
                "duplicates": 0,
                "total_llm_calls": 0,
                "total_tokens": 0,
                "total_elapsed_sec": 0,
            },
        }

    def update(self, **kwargs) -> None:
        with self._lock:
            self._data.update(kwargs)

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def snapshot(self) -> dict:
        with self._lock:
            return json_copy(self._data)

    def challenge(self, code: str) -> dict:
        with self._lock:
            return self._data["challenges"].setdefault(code, {
                "unique_code": code,
                "title": code,
                "difficulty": "unknown",
                "level": 0,
                "total_score": 0,
                "flag_count": 0,
                "correct_flag_count": 0,
                "is_completed": False,
                "container_status": "stopped",
                "container_addr": [],
                "status": "pending",     # pending | starting | solving | completed | failed
                "hints_used": 0,
                "started_at": None,
                "first_flag_sec": None,
                "solver_iterations": 0,
                "solver_status": "idle",
                "found_flags": [],
            })

    def log_event(self, msg: str) -> None:
        with self._lock:
            entry = {"ts": time.strftime("%H:%M:%S"), "msg": msg}
            self._data["events"].insert(0, entry)
            self._data["events"] = self._data["events"][:100]

    def log_submission(self, entry: dict) -> None:
        with self._lock:
            self._data["submissions"].insert(0, entry)
            self._data["submissions"] = self._data["submissions"][:200]


def json_copy(obj):
    import copy
    return copy.deepcopy(obj)
