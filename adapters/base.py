"""Platform Adapter abstraction.

Goal: hide TSec / Mock / future CTFd / HackTheBox differences behind a
single interface. The orchestrator depends on `PlatformAdapter` only.

Each adapter is responsible for:
  - listing challenges
  - starting a challenge (returning its reachable address list)
  - reading hints
  - submitting flags
  - closing challenges
  - classifying raw errors into canonical categories

The `Challenge` and `FlagResult` dataclasses carry enough information for
the orchestrator + frontend without leaking platform-specific keys.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Challenge:
    """Canonical challenge record.

    `raw` keeps the original platform payload for debugging / metrics.
    """

    unique_code: str
    title: str
    description: str
    difficulty: str
    level: int
    total_score: float
    flag_count: int
    correct_flag_count: int
    is_completed: bool
    container_addrs: list[str]
    container_status: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_paused(self) -> bool:
        return self.container_status not in ("available", "running")

    @property
    def progress_pct(self) -> int:
        if self.flag_count <= 0:
            return 0
        return min(100, round(self.correct_flag_count / self.flag_count * 100))


@dataclass
class FlagResult:
    """Canonical flag submission result.

    `duplicate` means: the platform already accepted this flag (idempotent
    success). `correct` means: this submission earned score. They are NOT
    mutually exclusive — TSec returns correct=False but duplicate=True.
    """

    correct: bool
    duplicate: bool
    awarded: float
    cumulative_score: float
    correct_flag_count: int
    total_flag_count: int
    matched_flag_index: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class HintResult:
    hint: str | None
    raw: dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):
    """Abstract base for any benchmark platform.

    Adapters are stateless w.r.t. the orchestrator; they just expose the
    platform API as methods.
    """

    name: str = "abstract"

    # ---------- challenge lifecycle ----------
    @abstractmethod
    def list_challenges(self) -> list[Challenge]: ...

    @abstractmethod
    def start_challenge(self, unique_code: str) -> list[str]:
        """Returns the reachable address(es) for the running container."""
        ...

    @abstractmethod
    def close_challenge(self, unique_code: str) -> None: ...

    @abstractmethod
    def get_hint(self, unique_code: str) -> HintResult: ...

    @abstractmethod
    def submit_flag(self, unique_code: str, flag: str) -> FlagResult: ...

    # ---------- error classification ----------
    @abstractmethod
    def is_auth_error(self, exc: BaseException) -> bool: ...

    @abstractmethod
    def is_rate_limited(self, exc: BaseException) -> bool: ...

    @abstractmethod
    def is_duplicate(self, exc: BaseException) -> bool: ...

    @abstractmethod
    def is_invalid_state(self, exc: BaseException) -> bool: ...

    @abstractmethod
    def is_not_found(self, exc: BaseException) -> bool: ...

    @abstractmethod
    def is_transient(self, exc: BaseException) -> bool: ...

    # ---------- helpers ----------
    def classify(self, exc: BaseException) -> str:
        """Single classification call returning a category string.

        Used by metrics / logging. Order matters: most specific first.
        """
        if self.is_duplicate(exc):
            return "duplicate"
        if self.is_invalid_state(exc):
            return "invalid_state"
        if self.is_auth_error(exc):
            return "auth_error"
        if self.is_rate_limited(exc):
            return "rate_limited"
        if self.is_not_found(exc):
            return "not_found"
        if self.is_transient(exc):
            return "transient"
        return "unknown"


def build_adapter(cfg: dict) -> PlatformAdapter:
    """Factory: pick an adapter by name from config.

    Lazy-import to avoid loading requests code on every run.
    """
    which = (cfg.get("platform") or {}).get("adapter", "tsec")
    if which == "tsec":
        from adapters.tsec import TSecAdapter

        return TSecAdapter(cfg)
    if which == "mock":
        from adapters.mock import MockAdapter

        return MockAdapter(cfg)
    raise ValueError(
        f"Unknown platform.adapter={which!r}. Supported: tsec, mock."
    )
