"""LLMClient 主类：anthropic 兼容 Messages API + agentic 工具循环 + parse_json。

文件拆分（拆 257 行 llm.py 为 3 个模块）：
  llm.py           - 本文件：LLMClient（init/chat/complete_text/parse_json/agentic）
  llm_client.py    - HTTP 客户端封装（endpoint/headers/requests session）
  llm_tools.py     - 工具 schema 定义（BASH_TOOL / PENTEST_TOOLS / _PT 工具注册表）

行为完全等价：拆分前后调同一个 LLMClient 拿到的响应一致。
"""
from __future__ import annotations

import json
import logging
import time

import requests

from solver.exec import run_command
from solver.llm_tools import BASH_TOOL, PENTEST_TOOLS, get_tool_command

LOG = logging.getLogger("solver.llm")


class LLMClient:
    """极简 anthropic 兼容客户端：chat / agentic 工具循环 / parse_json。

    base_url / api_key / model 从 config / env 读取（托管模式走 tsecbench 网关，
    本地走直连）。
    """

    def __init__(self, cfg: dict):
        m = cfg.get("model", {})
        self.provider = m.get("provider", "anthropic")
        self.model = m.get("model", "deepseek-v4-flash")
        self.base_url = (m.get("base_url") or "").rstrip("/")
        self.api_key = m.get("api_key") or ""
        self.max_tokens = int(m.get("max_tokens", 4096))
        self.timeout = float(m.get("timeout", 120))
        self.session = requests.Session()
        if not self.api_key:
            LOG.warning("LLM: api_key 为空（托管模式应注入 ANTHROPIC_AUTH_TOKEN）")

    # ---------- HTTP 端点（基础） ----------
    def _endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return self.base_url + "/messages"
        return self.base_url + "/v1/messages"

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    # ---------- 基础调用 ----------
    def chat(self, system: str, messages: list[dict], tools: list | None = None,
             max_tokens: int | None = None) -> dict:
        body = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        resp = self.session.post(self._endpoint(), headers=self._headers(),
                                 json=body, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def complete_text(self, system: str, user: str, max_tokens: int | None = None,
                      retries: int = 2) -> str:
        """单次调用（无工具），返回 assistant 最终文本。用于 Reason。

        LLM 失败不抛异常（返回空串），由调用方降级——避免 solver 崩溃。
        """
        for attempt in range(retries + 1):
            try:
                resp = self.chat(system, [{"role": "user", "content": user}],
                                 max_tokens=max_tokens)
                blocks = resp.get("content") or []
                return "\n".join(b.get("text", "") for b in blocks
                                 if b.get("type") == "text")
            except Exception as exc:
                LOG.warning("LLM complete_text 失败(第%s次): %s", attempt + 1, exc)
                time.sleep(1.0)
        return ""

    # ---------- JSON 提取 ----------
    @staticmethod
    def parse_json(text: str) -> dict | None:
        text = (text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return None

    # ---------- agentic 工具循环（Explore / Bootstrap） ----------
    def agentic(self, system: str, user: str, max_turns: int = 40,
                on_output=None, evidence_dir=None) -> dict:
        """AI 反复调 bash 工具直到给出最终答案。

        返回 {"text": 最终文本, "turns": n, "commands": [...], "outputs": [...]}

        evidence_dir: 如果提供，每条命令的 stdout/stderr 写到 evidence_dir/cmd_NNN.out。
        ⚠️ 2026-08-13 evidence 校验配套：_drain_flags 只信 evidence/**/*.out 里的 flag，
        agentic 模式不写盘 → 拿到 flag 也提交不了。这里让 agentic 写盘，
        _scan_session_result / cairn _drain_flags 才能扫到 flag。
        """
        messages = [{"role": "user", "content": user}]
        commands: list[str] = []
        outputs: list[dict] = []
        last_text = ""
        tools = [BASH_TOOL] + PENTEST_TOOLS
        if evidence_dir is not None:
            try:
                evidence_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                evidence_dir = None
        for turn in range(max_turns):
            try:
                resp = self.chat(system, messages, tools=tools)
            except Exception as exc:
                LOG.warning("LLM 调用失败: %s", exc)
                return {"text": last_text, "error": str(exc)[:200], "turns": turn,
                        "commands": commands, "outputs": outputs}
            blocks = resp.get("content") or []
            tool_calls = [b for b in blocks if b.get("type") == "tool_use"]
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            if texts:
                last_text = "\n".join(texts)
            if not tool_calls:
                return {"text": last_text, "turns": turn + 1,
                        "commands": commands, "outputs": outputs}
            # 标准 anthropic 消息流：先回传 assistant(tool_use)，再回传 user(tool_result)
            messages.append({"role": "assistant", "content": blocks})
            results = []
            for tc in tool_calls:
                tname = tc.get("name", "")
                args = tc.get("input") or {}
                cmd = get_tool_command(tname, args)
                commands.append(cmd)
                if on_output:
                    on_output(cmd)
                LOG.info("  └ %s[%d]: %s", tname, len(commands), cmd[:200])
                res = run_command(cmd, timeout=self.timeout)
                outputs.append(res)
                out_preview = res["output"].replace("\n", " ")[:300]
                LOG.info("  └ 输出: %s", out_preview)
                # ⚠️ 2026-08-13 evidence 落盘：让 cairn 扫得到 flag
                if evidence_dir is not None:
                    try:
                        ev_file = evidence_dir / f"cmd_{len(commands):03d}.out"
                        # 写命令本身 + 输出（exited code）
                        ev_file.write_text(
                            f"# cmd: {cmd}\n# exit: {res.get('exit', '?')}\n\n{res['output']}\n",
                            encoding="utf-8", errors="replace"
                        )
                    except OSError as exc:
                        LOG.debug("evidence 落盘失败 %s: %s", evidence_dir, exc)
                results.append({"type": "tool_result",
                                "tool_use_id": tc.get("id"),
                                "content": res["output"]})
            messages.append({"role": "user", "content": results})
            LOG.info("  └ 本轮 AI 文本: %s", last_text.replace("\n", " ")[:200])
        return {"text": last_text, "turns": max_turns,
                "commands": commands, "outputs": outputs}
