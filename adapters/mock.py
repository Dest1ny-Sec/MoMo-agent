"""Mock platform adapter：对接 scripts/mock_bench.py（本地端到端测速用）。

API 与真 TSec 同构（/openapi/v1/challenges + start/submit/close/hint），
差异：start 不真实起容器，直接返回靶场地址；close 无操作。
"""
from __future__ import annotations

import logging

import requests

from adapters.base import Challenge, FlagResult, HintResult, PlatformAdapter
from adapters.errors import NotFoundError, TransientError

LOG = logging.getLogger("platform.mock")


class MockAdapter(PlatformAdapter):
    name = "mock"

    def __init__(self, cfg: dict, timeout: float = 10.0):
        # 复用 platform.tsec 的 base_url 字段；本地默认 127.0.0.1:9900
        plat = cfg.get("platform", {}).get("tsec", {})
        bench = cfg.get("benchmark", {})
        self.base_url = (plat.get("base_url") or bench.get("base_url")
                         or "http://127.0.0.1:9900").rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, params: dict | None = None):
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        if resp.status_code >= 400:
            raise NotFoundError("mock_not_found", resp.text[:200], resp.status_code)
        return resp.json()

    def _post(self, path: str, params: dict | None = None, json_body: dict | None = None):
        resp = self.session.post(f"{self.base_url}{path}", params=params,
                                 json=json_body, timeout=self.timeout)
        if resp.status_code >= 400:
            raise NotFoundError("mock_not_found", resp.text[:200], resp.status_code)
        return resp.json()

    def list_challenges(self) -> list[Challenge]:
        data = self._get("/openapi/v1/challenges")
        out = []
        for ch in data if isinstance(data, list) else []:
            addrs = ch.get("container_addr") or []
            if not isinstance(addrs, list):
                addrs = [str(addrs)]
            out.append(Challenge(
                unique_code=ch.get("unique_code", ""),
                title=ch.get("description") or ch.get("unique_code", ""),
                description=ch.get("description", ""),
                difficulty=ch.get("difficulty", "unknown"),
                level=int(ch.get("level", 0) or 0),
                total_score=float(ch.get("total_score", 0) or 0),
                flag_count=int(ch.get("flag_count", 0) or 0),
                correct_flag_count=int(ch.get("correct_flag_count", 0) or 0),
                is_completed=bool(ch.get("is_completed", False)),
                container_addrs=[str(a) for a in addrs if a],
                container_status=ch.get("container_status", "stopped"),
                raw=ch,
            ))
        return out

    def start_challenge(self, unique_code: str) -> list[str]:
        data = self._post("/openapi/v1/challenges/start",
                          params={"unique_code": unique_code})
        addrs = data.get("container_addr") or []
        if not isinstance(addrs, list):
            addrs = [str(addrs)]
        return [str(a) for a in addrs if a]

    def close_challenge(self, unique_code: str) -> None:
        self._post("/openapi/v1/challenges/close", params={"unique_code": unique_code})

    def get_hint(self, unique_code: str) -> HintResult:
        data = self._get("/openapi/v1/challenges/hint",
                         params={"unique_code": unique_code})
        return HintResult(hint=data.get("hint"), raw=data)

    def submit_flag(self, unique_code: str, flag: str) -> FlagResult:
        data = self._post("/openapi/v1/challenges/submit",
                          json_body={"unique_code": unique_code, "flag": flag})
        return FlagResult(
            correct=bool(data.get("correct", False)),
            duplicate=False,
            awarded=float(data.get("awarded", 0) or 0),
            cumulative_score=float(data.get("cumulative_score", 0) or 0),
            correct_flag_count=int(data.get("correct_flag_count", 0) or 0),
            total_flag_count=int(data.get("total_flag_count", 0) or 0),
            matched_flag_index=data.get("matched_flag_index"),
            raw=data,
        )

    # 错误分类：mock 无鉴权/限流，统一按 transient 处理
    def is_auth_error(self, exc: BaseException) -> bool:
        return False
    def is_rate_limited(self, exc: BaseException) -> bool:
        return False
    def is_duplicate(self, exc: BaseException) -> bool:
        return False
    def is_invalid_state(self, exc: BaseException) -> bool:
        return False
    def is_not_found(self, exc: BaseException) -> bool:
        return isinstance(exc, NotFoundError)
    def is_transient(self, exc: BaseException) -> bool:
        return isinstance(exc, (requests.RequestException, TransientError))
