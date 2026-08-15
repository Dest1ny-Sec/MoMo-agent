"""SolverLoop prompts：所有 prompt 构造 + load_prompt + FLAG 正则/过滤。

从原 loop.py 抽出：
  FLAG_RE, is_plausible_flag, load_prompt
  _evidence_dir, _graph_snapshot（提示用 helper，但只读 main 类 attrs）
  所有 _*_prompt() 构造方法

依赖 GraphSolver 上的属性（被 mixin 间接继承）：
  self.ws, self.code, self.mission, self.graph
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FLAG_RE = re.compile(r"(?:flag|FLAG)\{[^{}\n]{1,200}\}")

# flag 合理性过滤：只拒绝明显非 flag 的（占位/太短/纯符号）。
# 注意：平台真实 flag 可能是 UUID 格式（如 e1-03 的 flag{ec401cf3-...}），
# 所以【不能拒绝 UUID】。防 AI 瞎猜靠"证据优先（只信命令输出）+ 提交上限"。
_PLACEHOLDER_INNERS = {"...", "xxx", "test", "your_flag", "flag", "flaag",
                       "mock", "placeholder", "redacted", "dummy"}


def is_plausible_flag(flag: str) -> bool:
    """判断一个 flag 候选是否值得上报（拒绝占位/太短/纯符号/乱码；UUID 放行）。"""
    if not FLAG_RE.fullmatch(flag):
        return False
    inner = flag.split("{", 1)[-1].rstrip("}")
    if inner in _PLACEHOLDER_INNERS:
        return False
    if inner.startswith("mock_"):
        return False  # 本地 mock 专属 flag，真实平台不会出现
    if len(inner) < 6:
        return False
    # 必须含可打印字母数字
    if not re.search(r"[a-zA-Z0-9]", inner):
        return False
    # 拒绝乱码：非 ASCII 字符 > 10% 视为不可信
    non_ascii = sum(1 for ch in inner if ord(ch) > 127 or ord(ch) < 32)
    if non_ascii > max(2, len(inner) * 0.1):
        return False
    # 拒绝包含反引号 / 控制字符（model 瞎猜常带 ` 或 \u3001 等）
    if "`" in inner or "\\u" in inner or "\\x" in inner:
        return False
    # 拒绝非 alphanumeric 标点（@ # ? ! 等）> 0 个（真实 flag 通常只含 [a-zA-Z0-9_-]）
    # 允许 1 个容差（UUID 里 4 个 - 已用 alphanumeric regex 包含，- 不算标点）
    punct = sum(1 for ch in inner if not ch.isalnum() and ch not in "_-")
    if punct > 0:
        return False
    return True


_PROMPTS: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """读 solver/prompts/<name>，缓存到模块 dict。"""
    if name not in _PROMPTS:
        _PROMPTS[name] = (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8")
    return _PROMPTS[name]


class PromptMixin:
    """所有 prompt 构造方法的 mixin。"""
    ws: Path
    code: str
    mission: dict
    graph: object  # Graph
    def _evidence_dir(self, session: str) -> Path:
        d = self.ws / "evidence" / session
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _graph_snapshot(self) -> str:
        return self.graph.snapshot()

    def _reason_prompt(self) -> str:
        return (load_prompt("reason.md")
                .replace("{graph}", self._graph_snapshot()))

    def _explore_prompt(self, intent: dict, session: str) -> str:
        return (load_prompt("explore.md")
                .replace("{graph}", self._graph_snapshot())
                .replace("{action}", intent.get("action", ""))
                .replace("{target}", self.mission.get("container_addr", ""))
                .replace("{description}", self.mission.get("description", ""))
                .replace("{evidence_dir}", str(self._evidence_dir(session))))

    def _explore_conclude_prompt(self, intent: dict, session: str) -> str:
        return (load_prompt("explore_conclude.md")
                .replace("{graph}", self._graph_snapshot())
                .replace("{action}", intent.get("action", ""))
                .replace("{target}", self.mission.get("container_addr", ""))
                .replace("{description}", self.mission.get("description", ""))
                .replace("{evidence_dir}", str(self._evidence_dir(session))))

    def _bootstrap_prompt(self, session: str) -> str:
        return (load_prompt("bootstrap.md")
                .replace("{graph}", self._graph_snapshot())
                .replace("{target}", self.mission.get("container_addr", ""))
                .replace("{description}", self.mission.get("description", ""))
                .replace("{flag_count}", str(self.mission.get("flag_count", "?")))
                .replace("{evidence_dir}", str(self._evidence_dir(session))))

    def _bootstrap_conclude_prompt(self, session: str) -> str:
        return (load_prompt("bootstrap_conclude.md")
                .replace("{graph}", self._graph_snapshot())
                .replace("{target}", self.mission.get("container_addr", ""))
                .replace("{description}", self.mission.get("description", ""))
                .replace("{flag_count}", str(self.mission.get("flag_count", "?")))
                .replace("{evidence_dir}", str(self._evidence_dir(session))))
