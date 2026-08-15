"""严格契约：claude worker JSON 解析 + 形状校验（port cairn contracts.py + output_parser.py）。

SessionWorker 每次输出都要过这里：先 extract_json_object 从 stdout 抠出 JSON，
再用 validate_for_phase 按 phase 校验形状（accepted 包裹 + data 结构）。
任何不符都 raise ValueError，由 worker 层走 conclude 兜底，绝不静默接受脏输出。
"""
from __future__ import annotations

import json
import re
from typing import Any

FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_json_object(text: str) -> dict:
    """从 stdout 提取第一个 JSON 对象。port cairn output_parser：
    整段 json.loads → fenced 块 → 每个 '{' 处 raw_decode（处理输出前带日志/思考文字）。
    找不到抛 ValueError。"""
    decoder = json.JSONDecoder()
    seen: set[str] = set()
    for candidate in _candidate_segments(text):
        segment = candidate.strip()
        if not segment or segment in seen:
            continue
        seen.add(segment)
        try:
            parsed = json.loads(segment)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, dict):
                return parsed
        for start in _object_start_positions(segment):
            try:
                parsed, _end = decoder.raw_decode(segment[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError("no JSON object found in output")


def _candidate_segments(text: str) -> list[str]:
    segments = [text.strip()]
    segments.extend(m.group(1).strip() for m in FENCED_BLOCK_RE.finditer(text))
    return segments


def _object_start_positions(text: str) -> list[int]:
    return [i for i, ch in enumerate(text) if ch == "{"]


def parse_json_output(stdout: str) -> dict:
    return extract_json_object(stdout)


# ---------- accepted 包裹 ----------
def _unwrap_wrapped_payload(payload: Any) -> tuple[bool | None, dict | None]:
    """accepted=True→(True,data)；False→(False,None)；缺失→(None,None)。"""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    accepted = payload.get("accepted")
    if accepted is False:
        return False, None
    if accepted is True:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        return True, data
    return None, None


# ---------- explore / explore_conclude ----------
def validate_explore_payload(payload: dict) -> tuple[str, str | None]:
    """合法: {"accepted":true,"data":{"description":"..."}} 或裸 {"description":"..."}。
    返回 (kind, description)。"""
    accepted, data = _unwrap_wrapped_payload(payload)
    if accepted is False:
        return "rejected", None
    if accepted is None:
        if not (isinstance(payload, dict) and set(payload) == {"description"}):
            raise ValueError("accepted must be true or false")
        data = payload
    if not isinstance(data, dict):
        raise ValueError("accepted must be true or false")
    d = data.get("description")
    if not isinstance(d, str) or not d.strip():
        raise ValueError("description is required")
    return "fact", d.strip()


# ---------- bootstrap execute ----------
def validate_bootstrap_execute_payload(payload: dict) -> tuple[str, dict | None]:
    """合法: data={"fact":{"description":"..."}}（可带 complete）。
    返回 (kind, {"fact_description":..., "complete_description":...|None})。"""
    accepted, data = _unwrap_wrapped_payload(payload)
    if accepted is False:
        return "rejected", None
    if accepted is None:
        raise ValueError("accepted must be true or false")
    if not isinstance(data, dict):
        raise ValueError("accepted must be true or false")
    fact = data.get("fact")
    if not isinstance(fact, dict) or not isinstance(fact.get("description"), str) \
            or not fact["description"].strip():
        raise ValueError("fact.description is required")
    out: dict[str, Any] = {"fact_description": fact["description"].strip(),
                           "complete_description": None}
    complete = data.get("complete")
    if complete is not None:
        if not isinstance(complete, dict) or not isinstance(complete.get("description"), str) \
                or not complete["description"].strip():
            raise ValueError("complete.description is required")
        out["complete_description"] = complete["description"].strip()
        return "complete", out
    return "fact", out


# ---------- bootstrap conclude ----------
def validate_bootstrap_conclude_payload(payload: dict) -> tuple[str, str | None]:
    """合法: data={"fact":{"description":"..."}}。出现 complete 键直接拒。"""
    accepted, data = _unwrap_wrapped_payload(payload)
    if accepted is False:
        return "rejected", None
    if accepted is None:
        raise ValueError("accepted must be true or false")
    if not isinstance(data, dict):
        raise ValueError("accepted must be true or false")
    extra = set(data) - {"fact"}
    if extra:
        raise ValueError(f"unexpected keys in conclude payload: {extra}")
    fact = data.get("fact")
    if not isinstance(fact, dict) or not isinstance(fact.get("description"), str) \
            or not fact["description"].strip():
        raise ValueError("fact.description is required")
    return "fact", fact["description"].strip()


# ---------- reason ----------
def validate_reason_payload(payload: dict, open_intents_empty: bool,
                            max_intents: int) -> tuple[str, Any]:
    """合法: complete / intents / noop(空 data)。返回 (kind, data)。"""
    accepted, data = _unwrap_wrapped_payload(payload)
    if accepted is False:
        return "rejected", None
    if accepted is None:
        raise ValueError("accepted must be true or false")
    if not isinstance(data, dict):
        raise ValueError("accepted must be true or false")
    complete = data.get("complete")
    intents = data.get("intents")
    # 兼容单数 intent
    if intents is None and isinstance(data.get("intent"), dict):
        intents = [data["intent"]]
    if complete is not None:
        if intents is not None:
            raise ValueError("complete and intents cannot coexist")
        if not (isinstance(complete, dict) and "from" in complete
                and "description" in complete):
            raise ValueError("invalid complete payload")
        return "complete", complete
    if intents is not None:
        if not isinstance(intents, list):
            raise ValueError("intents must be an array")
        for i, it in enumerate(intents):
            if not (isinstance(it, dict) and "from" in it and "description" in it):
                raise ValueError(f"invalid intent at index {i}")
        if not intents and open_intents_empty:
            raise ValueError("intents must not be empty when open_intents is empty")
        intents = intents[:max_intents]
        if not intents:
            return "noop", None
        return "intents", intents
    if open_intents_empty:
        raise ValueError("intents is required when open_intents is empty")
    return "noop", None


# ---------- 分发 ----------
def validate_for_phase(phase: str, payload: dict, **kwargs) -> tuple[str, Any]:
    if phase in ("explore", "explore_conclude"):
        return validate_explore_payload(payload)
    if phase == "bootstrap":
        return validate_bootstrap_execute_payload(payload)
    if phase == "bootstrap_conclude":
        return validate_bootstrap_conclude_payload(payload)
    if phase == "reason":
        return validate_reason_payload(payload, **kwargs)
    raise ValueError(f"unknown phase: {phase}")
