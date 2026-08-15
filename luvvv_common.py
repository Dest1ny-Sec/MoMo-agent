"""Luvvv-agent 共享基础模块：配置加载 / flag 验证 / 日志 / .env 解析。"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "config.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def localnow() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE, supports # comments and "..." quotes.

    Only sets a value if the key is not already in os.environ (existing
    process env wins over .env). This is the standard 12-factor rule.
    """
    env: dict[str, str] = {}
    if not path.exists():
        return env
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            # strip surrounding quotes
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            if not key:
                continue
            if key not in os.environ:
                os.environ[key] = val
            env[key] = val
    except OSError:
        pass
    return env


# Module-level: load .env once at import time so adapters see them.
_load_dotenv(ROOT / ".env")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 从环境变量兜底填充 benchmark 凭证
    b = cfg.setdefault("benchmark", {})
    if not b.get("token"):
        b["token"] = os.environ.get("BENCHMARK_TOKEN", "")
    if not b.get("base_url"):
        b["base_url"] = os.environ.get("BENCHMARK_BASE_URL", "")

    # 同步到老 benchmark.* 到新的 platform.tsec.*（向后兼容）
    p = cfg.setdefault("platform", {})
    tsec = p.setdefault("tsec", {})
    if not tsec.get("token"):
        tsec["token"] = b.get("token", "")
    if not tsec.get("base_url"):
        tsec["base_url"] = b.get("base_url", "")

    # 模型凭证兜底（环境变量 > config.json）
    # 托管模式下平台注入 ANTHROPIC_BASE_URL（网关地址），必须覆盖 config.json
    m = cfg.setdefault("model", {})
    env_base = os.environ.get("ANTHROPIC_BASE_URL", "")
    if env_base:
        m["base_url"] = env_base
    elif not m.get("base_url"):
        m["base_url"] = os.environ.get("ANTHROPIC_BASE_URL", "")
    if not m.get("api_key"):
        m["api_key"] = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    # 模型名：env 优先
    env_model = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("LUVVV_MODEL")
    if env_model:
        m["model"] = env_model
    if not m.get("reason_model"):
        # reason 默认复用 explore 模型
        m["reason_model"] = m.get("model", "")

    # provider 覆盖（mock 模式用：主进程改 cfg 后传给子进程）
    env_provider = os.environ.get("LUVVV_MODEL_PROVIDER")
    if env_provider:
        m["provider"] = env_provider

    return cfg


def get_flag_regex(cfg: dict) -> re.Pattern:
    pattern = cfg["flag"]["pattern"]
    return re.compile(pattern, re.DOTALL)


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
