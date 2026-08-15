"""TSec Benchmark platform adapter.

Implements the canonical PlatformAdapter against Tencent Security's
TSec openapi (https://<host>/openapi/v1/challenges/...).

Auth is via `BENCHMARK_TOKEN` header. Errors are normalized into our
canonical PlatformError subclasses (see platform/errors.py).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from adapters.base import Challenge, FlagResult, HintResult, PlatformAdapter
from adapters.errors import (
    AuthError,
    DuplicateFlagError,
    InvalidStateError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    TransientError,
)

LOG = logging.getLogger("platform.tsec")


# TSec's openapi error code mapping. Centralized here so we don't scatter
# raw `code` strings across the orchestrator.
_TSEC_KNOWN_CODES = {
    "auth_error",        # 401: token invalid / expired
    "rate_limited",      # 429: throttled
    "duplicate",         # flag already submitted for this challenge
    "invalid_state",     # challenge closed / expired / team eliminated
    "challenge_not_found",
    "task_not_found",
    "internal_error",    # 5xx-ish
}


class TSecAdapter(PlatformAdapter):
    name = "tsec"

    def __init__(self, cfg: dict, timeout: float = 15.0, max_retries: int = 2):
        self.cfg = cfg
        plat = cfg.get("platform", {}).get("tsec", {})
        # 兼容旧字段：benchmark.token / benchmark.base_url 也可读
        bench = cfg.get("benchmark", {})
        self.base_url = (
            plat.get("base_url")
            or bench.get("base_url")
            or ""
        ).rstrip("/")
        self.token = plat.get("token") or bench.get("token") or ""
        self.timeout = float(plat.get("timeout", timeout))
        self.max_retries = int(plat.get("max_retries", max_retries))
        self.session = requests.Session()
        if not self.base_url:
            LOG.warning("TSecAdapter: base_url is empty; run will fail at first call")

    # ---------- low-level HTTP ----------
    def _headers(self) -> dict:
        return {
            "BENCHMARK_TOKEN": self.token,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body: dict | None = None) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.request(
                    method, url, params=params, json=json_body,
                    headers=self._headers(), timeout=self.timeout,
                )
                break
            except requests.RequestException as exc:
                last_exc = exc
                LOG.warning("网络异常 %s %s 第%s次: %s", method, path, attempt + 1, exc)
                time.sleep(1.5)
        else:
            raise NetworkError("network_error", f"网络连接失败: {last_exc}")

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                raise TransientError(
                    "http_error",
                    f"HTTP {resp.status_code}: {resp.text[:200]}",
                    resp.status_code,
                )
            code = body.get("code", "unknown")
            message = body.get("message", resp.text[:200])
            # Map TSec's code into our exception types
            if code in ("auth_error",) or resp.status_code in (401, 403):
                raise AuthError(code, message, resp.status_code)
            if code == "duplicate":
                raise DuplicateFlagError(code, message, resp.status_code)
            if code == "invalid_state":
                raise InvalidStateError(code, message, resp.status_code)
            if code in ("challenge_not_found", "task_not_found") or resp.status_code == 404:
                raise NotFoundError(code, message, resp.status_code)
            if code == "rate_limited" or resp.status_code == 429:
                raise RateLimitError(code, message, resp.status_code)
            if resp.status_code >= 500:
                raise TransientError(code, message, resp.status_code)
            # Unknown — surface as a transient so we don't silently drop
            raise TransientError(code, message, resp.status_code)

        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {}

    # ---------- challenge lifecycle ----------
    def list_challenges(self) -> list[Challenge]:
        _, data = self._request("GET", "/openapi/v1/challenges")
        if not isinstance(data, list):
            return []
        out: list[Challenge] = []
        for ch in data:
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
        try:
            _, data = self._request(
                "POST", "/openapi/v1/challenges/start",
                params={"unique_code": unique_code},
            )
        except InvalidStateError:
            # already started → refetch addr from list
            LOG.info("start %s returned invalid_state; treating as already-started", unique_code)
            challenges = self.list_challenges()
            for ch in challenges:
                if ch.unique_code == unique_code:
                    return ch.container_addrs
            raise
        addrs = (data or {}).get("container_addr") or []
        if not isinstance(addrs, list):
            addrs = [str(addrs)]
        return [str(a) for a in addrs if a]

    def close_challenge(self, unique_code: str) -> None:
        try:
            self._request(
                "POST", "/openapi/v1/challenges/close",
                params={"unique_code": unique_code},
            )
        except (InvalidStateError, NotFoundError) as exc:
            # closing an already-closed challenge is fine
            LOG.info("close %s skipped: %s", unique_code, exc.code)

    def get_hint(self, unique_code: str) -> HintResult:
        _, data = self._request(
            "GET", "/openapi/v1/challenges/hint",
            params={"unique_code": unique_code},
        )
        hint = (data or {}).get("hint") if isinstance(data, dict) else None
        return HintResult(hint=hint, raw=data if isinstance(data, dict) else {})

    def submit_flag(self, unique_code: str, flag: str) -> FlagResult:
        """Submit and return canonical result.

        平台语义（tsec-benchmark SDK）：
          - 正确 flag（首次）→ HTTP 200, correct=true, matched_flag_index=<索引>
          - 错误 flag       → HTTP 200, correct=false, matched_flag_index=None
          - 重复提交        → HTTP 409, code=duplicate（由 DuplicateFlagError 捕获）
        旧实现把"错误 flag"（correct=false + matched_flag_index=None）误判成"重复提交"，
        导致错误 flag 显示为 `≡ 重复提交` 而永远不报 `✗ 错误`（c-03/c-06 实际没得分）。
        """
        try:
            _, data = self._request(
                "POST", "/openapi/v1/challenges/submit",
                json_body={"unique_code": unique_code, "flag": flag},
            )
        except DuplicateFlagError as exc:
            return FlagResult(
                correct=False, duplicate=True,
                awarded=0.0, cumulative_score=0.0,
                correct_flag_count=0, total_flag_count=0,
                raw={"code": exc.code, "message": exc.message},
            )
        data = data if isinstance(data, dict) else {}
        correct = bool(data.get("correct", False))
        idx = data.get("matched_flag_index")
        # 真正的重复 = 平台返回 code=duplicate（409 已被上面捕获）；HTTP 200 的
        # correct=false + matched_flag_index=None 一律视为"错误 flag"，不是重复。
        body_code = data.get("code", "")
        duplicate = body_code == "duplicate"
        if not correct and not duplicate:
            LOG.info("✗ [%s] 平台拒绝 flag: %s (msg=%s)",
                     unique_code, flag[:60], str(data.get("message", ""))[:120])
        return FlagResult(
            correct=correct,
            duplicate=duplicate,
            awarded=float(data.get("awarded", 0) or 0),
            cumulative_score=float(data.get("cumulative_score", 0) or 0),
            correct_flag_count=int(data.get("correct_flag_count", 0) or 0),
            total_flag_count=int(data.get("total_flag_count", 0) or 0),
            matched_flag_index=idx,
            raw=data,
        )

    # ---------- error classification ----------
    def is_auth_error(self, exc: BaseException) -> bool:
        return isinstance(exc, AuthError)

    def is_rate_limited(self, exc: BaseException) -> bool:
        return isinstance(exc, RateLimitError)

    def is_duplicate(self, exc: BaseException) -> bool:
        return isinstance(exc, DuplicateFlagError)

    def is_invalid_state(self, exc: BaseException) -> bool:
        return isinstance(exc, InvalidStateError)

    def is_not_found(self, exc: BaseException) -> bool:
        return isinstance(exc, NotFoundError)

    def is_transient(self, exc: BaseException) -> bool:
        return isinstance(exc, (NetworkError, TransientError))
