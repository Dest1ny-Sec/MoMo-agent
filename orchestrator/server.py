"""简易状态服务：前端面板 + JSON 接口（线程内运行，无额外依赖）。"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from luvvv_common import ROOT

LOG = logging.getLogger("server")

FRONTEND = ROOT / "frontend" / "index.html"


class StatusHandler(BaseHTTPRequestHandler):
    store = None  # 由 factory 注入

    def log_message(self, fmt, *args):
        return  # 静默 access log

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            if FRONTEND.exists():
                self._send(200, FRONTEND.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"frontend/index.html not found")
        elif self.path == "/api/status":
            self._send(200, json.dumps(self.store.snapshot(), ensure_ascii=False).encode("utf-8"))
        elif self.path.startswith("/api/progress/"):
            # /api/progress/<code>?tail=20  →  该题 progress.jsonl 尾 N 条
            code = self.path[len("/api/progress/"):].split("?")[0]
            tail = 20
            try:
                from urllib.parse import parse_qs
                qs = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
                tail = int(qs.get("tail", ["20"])[0])
            except Exception:
                pass
            prog_path = ROOT / "workspace" / code / "progress.jsonl"
            if not prog_path.exists():
                self._send(200, json.dumps({"code": code, "events": []}, ensure_ascii=False).encode("utf-8"))
                return
            try:
                lines = prog_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            events = []
            for line in lines[-tail:]:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
            self._send(200, json.dumps({"code": code, "events": events, "total": len(lines)}, ensure_ascii=False).encode("utf-8"))
        elif self.path.startswith("/api/control"):
            # /api/control?code=X  →  回显该题暂停/优先级控制状态
            from urllib.parse import parse_qs
            qs = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            code = qs.get("code", [""])[0]
            if not code or _bad_code(code):
                self._send(400, json.dumps({"ok": False, "error": "bad code"}).encode("utf-8"))
                return
            self._send(200, json.dumps({
                "code": code, "paused": bool(self._read_control(code).get("paused", False)),
                "priority": int(self._read_control(code).get("priority", 0) or 0),
            }, ensure_ascii=False).encode("utf-8"))
        elif self.path.startswith("/static/"):
            # /static/vendor/x.js -> frontend/vendor/x.js
            rel = self.path[len("/static/"):]
            f = ROOT / "frontend" / rel
            if f.exists() and f.is_file():
                ctype = "application/javascript" if f.suffix == ".js" else "application/octet-stream"
                self._send(200, f.read_bytes(), ctype)
            else:
                self._send(404, b"static not found")
        else:
            self._send(404, b"not found")

    # ---- 控制通道辅助 ----
    def _read_control(self, code: str) -> dict:
        p = ROOT / "workspace" / code / "control.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _write_control(self, code: str, **fields) -> None:
        p = ROOT / "workspace" / code / "control.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        cur = self._read_control(code)
        cur.update(fields)
        p.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")

    def do_POST(self):
        """控制通道：
          POST /api/control/pause      {code}         暂停该题（scheduler 关容器、不再排）
          POST /api/control/resume     {code}         恢复该题（重新入队）
          POST /api/control/priority   {code, n}      设优先级（n 越大越先解）
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) or b"{}"
            body = json.loads(raw)
        except Exception:
            self._send(400, json.dumps({"ok": False, "error": "bad json"}).encode("utf-8"))
            return

        if self.path == "/api/control/pause":
            code = str(body.get("code") or "").strip()
            if not code or _bad_code(code):
                self._send(400, json.dumps({"ok": False, "error": "bad code"}).encode("utf-8"))
                return
            self._write_control(code, paused=True)
            LOG.info("控制: 暂停 %s", code)
            self._send(200, json.dumps({"ok": True, "code": code, "paused": True}).encode("utf-8"))
        elif self.path == "/api/control/resume":
            code = str(body.get("code") or "").strip()
            if not code or _bad_code(code):
                self._send(400, json.dumps({"ok": False, "error": "bad code"}).encode("utf-8"))
                return
            self._write_control(code, paused=False)
            LOG.info("控制: 恢复 %s", code)
            self._send(200, json.dumps({"ok": True, "code": code, "paused": False}).encode("utf-8"))
        elif self.path == "/api/control/priority":
            code = str(body.get("code") or "").strip()
            if not code or _bad_code(code):
                self._send(400, json.dumps({"ok": False, "error": "bad code"}).encode("utf-8"))
                return
            try:
                prio = int(body.get("priority", 0))
            except (TypeError, ValueError):
                self._send(400, json.dumps({"ok": False, "error": "priority must be int"}).encode("utf-8"))
                return
            self._write_control(code, priority=prio)
            LOG.info("控制: %s 优先级=%d", code, prio)
            self._send(200, json.dumps({"ok": True, "code": code, "priority": prio}).encode("utf-8"))
        else:
            self._send(404, b"not found")


def _bad_code(code: str) -> bool:
    """路径越界防护：code 只能是普通 unique_code，不允许路径分隔符。"""
    return ("/" in code or "\\" in code or ".." in code or code.startswith("."))


def start_status_server(store, host: str, port: int) -> threading.Thread:
    handler = type("CairnHandler", (StatusHandler,), {"store": store})
    httpd = ThreadingHTTPServer((host, port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True, name="status-server")
    t.start()
    LOG.info("前端面板: http://%s:%s", host, port)
    return t
