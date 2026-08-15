"""量化指标埋点：落 CSV，供答辩与 dashboard 使用。

PR1 修复：
  - log_challenge_result 加 _logged_challenges 去重，避免 close 重入写多行
  - log_llm 现在能被 solver.loop 调用（之前从未被调用）
"""
from __future__ import annotations

import csv
import logging
import time
from pathlib import Path

from luvvv_common import ensure_dir

LOG = logging.getLogger("metrics")


class Metrics:
    def __init__(self, root: Path):
        self.root = ensure_dir(root / "metrics")
        self.start_wall = time.time()
        self._flag_path = self.root / "flags.csv"
        self._llm_path = self.root / "llm_calls.csv"
        self._challenge_path = self.root / "challenges.csv"
        self._ensure_csv(self._flag_path, ["ts", "unique_code", "flag", "correct", "awarded", "duplicate", "hint_used"])
        self._ensure_csv(self._llm_path, ["ts", "unique_code", "phase", "model", "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd", "latency_ms"])
        self._ensure_csv(self._challenge_path, ["unique_code", "title", "difficulty", "status", "flag_count", "correct_flags", "score", "first_flag_sec", "solver_iterations", "hints_used"])
        # PR1.6: 防 challenges.csv 重复行
        self._logged_challenges: set[str] = set()
        # 读已有文件里已经写过的 unique_code（防止重启时 _logged_challenges 被清空）
        try:
            with open(self._challenge_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = (row.get("unique_code") or "").strip()
                    if code:
                        self._logged_challenges.add(code)
        except Exception:
            pass

    @staticmethod
    def _ensure_csv(path: Path, header: list[str]) -> None:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(header)

    def _append(self, path: Path, row: list) -> None:
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def log_flag(self, unique_code: str, flag: str, correct: bool, awarded: float,
                 duplicate: bool, hint_used: bool) -> None:
        self._append(self._flag_path, [
            time.strftime("%Y-%m-%d %H:%M:%S"), unique_code, flag,
            "1" if correct else "0", round(awarded, 2),
            "1" if duplicate else "0", "1" if hint_used else "0",
        ])

    def log_llm(self, unique_code: str, phase: str, model: str, pt: int, ct: int,
                 cost_usd: float, latency_ms: int) -> None:
        """Record one LLM call. Called by solver.loop (PR1.6)."""
        self._append(self._llm_path, [
            time.strftime("%Y-%m-%d %H:%M:%S"), unique_code, phase, model,
            pt, ct, pt + ct, round(cost_usd, 4), latency_ms,
        ])

    def log_challenge_result(self, row: dict) -> None:
        """Record one challenge final result. PR1.6: 去重，重复 close 不会写多行。"""
        code = (row.get("unique_code") or "").strip()
        if not code:
            return
        if code in self._logged_challenges:
            LOG.debug("challenges.csv 已记录过 %s，跳过", code)
            return
        self._logged_challenges.add(code)
        self._append(self._challenge_path, [
            code, row.get("title", ""), row.get("difficulty", ""),
            row.get("status", ""), row.get("flag_count", 0), row.get("correct_flags", 0),
            round(row.get("score", 0), 2), row.get("first_flag_sec") or "",
            row.get("solver_iterations", 0), row.get("hints_used", 0),
        ])

    def elapsed_sec(self) -> float:
        return time.time() - self.start_wall
