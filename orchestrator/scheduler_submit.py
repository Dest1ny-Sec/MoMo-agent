"""Scheduler 提交循环：drain flags_found.jsonl → 提交 → 记录。

从原 scheduler.py 抽出的方法：
  _drain_flags, _submit_flag
  _sync_platform_cfc   ← 新增：每 30s 拉平台 list 对比 cfc，发现 solver 自提交立即 close+kill
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

LOG = logging.getLogger("scheduler.submit")


class SubmitMixin:
    """提交 mixin：从 flags_found.jsonl 读 flag，调 adapter.submit_flag，记录结果。"""
    workspace: Path
    _submitted: dict
    _seen_flag_files: dict
    _wrong_sub_count: dict
    _max_wrong_sub: int
    adapter: object
    store: object
    metrics: object
    _task_ended: bool
    _close: callable  # Scheduler._close
    _completed_count: callable  # Scheduler._completed_count
    _last_cfc_sync_ts: float  # 上次同步平台 cfc 的时间戳
    _seen_cfc: dict  # code -> 上次看到的 cfc

    def _sync_platform_cfc(self) -> None:
        """每 30s 拉一次平台 list，对比 correct_flag_count。
        关键：solver 有时会自己调 submit API 绕开 cairn（自提交），cairn 必须从平台
        反向发现这种"瞒报"情况。差值 → 标记完成 + close + kill solver。
        """
        now = time.time()
        if now - getattr(self, "_last_cfc_sync_ts", 0) < 30:
            return
        self._last_cfc_sync_ts = now
        try:
            challenges = self.adapter.list_challenges()
        except Exception as exc:
            LOG.warning("list_challenges 失败: %s", exc)
            return
        for ch in challenges:
            code = ch.unique_code
            cfc = int(getattr(ch, "correct_flag_count", 0) or 0)
            fc = int(getattr(ch, "flag_count", 0) or 0)
            if code not in getattr(self, "_seen_cfc", {}):
                if not hasattr(self, "_seen_cfc"):
                    self._seen_cfc = {}
                self._seen_cfc[code] = cfc
                continue
            if cfc > self._seen_cfc.get(code, 0):
                # 平台 cfc 增长 → 有人提交了（solver 自提交 或 我们提交过没记的）
                delta = cfc - self._seen_cfc[code]
                LOG.info("⚡ 平台 cfc 增长 %s: %d→%d（%d 个新 flag，solver 自提交？），关闭容器",
                         code, self._seen_cfc[code], cfc, delta)
                self._seen_cfc[code] = cfc
                # 更新 store + 标记完成
                st = self.store.challenge(code)
                st["correct_flag_count"] = cfc
                if fc > 0 and cfc >= fc:
                    st["is_completed"] = True
                    st["status"] = "completed"
                    # 累加 total_score（按 total_score × cfc/fc 推算）
                    ts = float(getattr(ch, "total_score", 0) or 0)
                    add = ts * cfc / fc if fc else 0
                    st["cumulative_score"] = add
                    cur = self.store.get("total_score", 0)
                    self.store.update(total_score=round(cur + add - st.get("_last_added", 0), 2),
                                      completed_challenges=self._completed_count())
                    st["_last_added"] = add
                # 关键：杀掉 solver（如果还在跑）+ close 容器
                self._kill_challenge(code)
                self._close(code)

    def _flag_in_evidence(self, code: str, flag: str) -> bool:
        """Evidence 校验：flag 必须出现在 workspace/<code>/evidence/**/*.out 里。

        防止 solver 瞎猜 UUID 格式 flag（之前 a-03 在 LLM 文本里编 4 个真格式 UUID
        flag{2a51614f-...} 都被 is_plausible_flag 放行 → cairn 30s 内全提交平台）。
        真实 flag 必然先出现在 evidence/<session>/cmd_*.out 的真实命令输出里。
        """
        ev_root = self.workspace / code / "evidence"
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

    def _drain_flags(self, code: str) -> None:
        """读 flags_found.jsonl 新行 → 逐条调 _submit_flag。
        ⚠️ 2026-08-13 加 is_plausible_flag 过滤：之前 f2-01/04/05 solver 把 unicode 乱码
        写进 flags_found.jsonl，cairn 不加过滤就全提交，每题 5-9 次拒。
        ⚠️ 2026-08-13 加 evidence 校验：之前 a-03 solver 在 LLM 文本里编 4 个真格式
        UUID flag{2a51614f-...} 都被 is_plausible_flag 放行 → cairn 30s 内全提交平台
        → 100/100 配额会耗尽。Evidence 校验保证只信命令真实输出。"""
        # 先做平台 cfc 同步（捕获 solver 自提交情况）
        self._sync_platform_cfc()
        flag_file = self.workspace / code / "flags_found.jsonl"
        if not flag_file.exists():
            return
        offset = self._seen_flag_files.get(code, 0)
        try:
            lines = flag_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        # 导入 is_plausible_flag 复用 loop.py 的过滤
        try:
            from solver.loop_prompts import is_plausible_flag
        except Exception:
            is_plausible_flag = lambda f: True  # 兜底
        import re
        FLAG_RE = re.compile(r"(?:flag|FLAG)\{[^{}\n]{1,200}\}")
        for idx, line in enumerate(lines[offset:], offset):
            try:
                entry = json.loads(line)
            except Exception:
                self._seen_flag_files[code] = idx
                continue
            self._seen_flag_files[code] = idx + 1
            flag = (entry.get("flag") or "").strip()
            if not flag:
                continue
            # 必须在 FLAG{...} 格式 + 通过 is_plausible_flag
            if not FLAG_RE.fullmatch(flag):
                LOG.debug("[%s] skip non-FLAG-format: %s", code, flag[:40])
                continue
            if not is_plausible_flag(flag):
                LOG.warning("[%s] skip implausible flag（乱码/瞎猜）: %s", code, flag[:60])
                continue
            # ⚠️ Evidence 校验：flag 必须出现在 evidence/**/*.out 的真实命令输出里
            # （防 AI 在 LLM 文本里编 UUID 瞎猜提交）
            if not self._flag_in_evidence(code, flag):
                LOG.warning("[%s] skip flag without evidence（AI 瞎猜/无源）: %s", code, flag[:60])
                continue
            # 错误提交已达上限 → 不再提交该题的新 flag（防瞎猜刷屏）
            if self._wrong_sub_count.get(code, 0) >= self._max_wrong_sub:
                continue
            self._submit_flag(code, flag)

    def _submit_flag(self, code: str, flag: str) -> None:
        """单条 flag 提交：调平台 API，记录结果到 store/metrics，必要时关题。"""
        done = self._submitted.setdefault(code, set())
        if flag in done:
            return
        st = self.store.challenge(code)
        try:
            result = self.adapter.submit_flag(code, flag)
        except Exception as exc:
            category = self.adapter.classify(exc)
            if category == "invalid_state":
                self._task_ended = True
                self.store.update(task_ended=True)
                self.store.log_event("任务已结束(超时/停止)")
                return
            LOG.warning("提交 %s flag 失败 [%s]: %s", code, category, exc)
            return

        correct = result.correct
        duplicate = result.duplicate
        awarded = result.awarded
        cumulative = result.cumulative_score
        correct_count = result.correct_flag_count or st.get("correct_flag_count", 0)
        total_count = result.total_flag_count or st.get("flag_count", 0)

        self.metrics.log_flag(code, flag, correct, awarded, duplicate, False)
        if correct:
            done.add(flag)
            st["correct_flag_count"] = correct_count
            st["cumulative_score"] = cumulative
            # 关键：scheduler 自己提交成功后，同步平台 cfc 到 _seen_cfc，
            # 否则 _sync_platform_cfc 会把"我们自己的提交"误判成 solver 自提交 → 重复计分 + 误关容器
            self._seen_cfc[code] = correct_count
            if st.get("first_flag_sec") is None:
                st["first_flag_sec"] = round(self.metrics.elapsed_sec(), 1)
            self.store.update(total_score=round(self.store.get("total_score", 0) + awarded, 2))
            self.store.log_submission({"ts": time.strftime("%H:%M:%S"), "code": code,
                                       "flag": flag, "result": "correct",
                                       "awarded": awarded, "cumulative": cumulative})
            LOG.info("✓ %s flag 正确 +%s 累计=%s 进度=%s/%s",
                     code, awarded, cumulative, correct_count, total_count)
            if total_count > 0 and correct_count >= total_count:
                st["is_completed"] = True
                st["status"] = "completed"
                self.store.update(completed_challenges=self._completed_count())
                self._close(code)
        elif duplicate:
            done.add(flag)
            LOG.info("≡ %s flag 重复提交，跳过", code)
        else:
            done.add(flag)
            self._wrong_sub_count[code] = self._wrong_sub_count.get(code, 0) + 1
            self.store.log_submission({"ts": time.strftime("%H:%M:%S"), "code": code,
                                       "flag": flag, "result": "wrong"})
            LOG.info("✗ %s flag 错误: %s（错误%d/%d）", code, flag[:60],
                     self._wrong_sub_count[code], self._max_wrong_sub)

        with open(self.workspace / code / "submission_results.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"flag": flag, "correct": correct, "awarded": awarded}) + "\n")
