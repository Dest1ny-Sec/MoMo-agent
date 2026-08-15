#!/usr/bin/env python3
"""Mock TSec benchmark server + 内置 3 道不同难度靶场，用于本地端到端测试。

端口：
  9900  TSec API（challenges/start/submit/close，与真平台同构）
  9901  mock-easy-001  首页直接泄露 flag
  9902  mock-med-002   robots.txt → /secret-page
  9903  mock-hard-003  /api/check?id=<n>，id=42 返回 flag

用法：python3 scripts/mock_bench.py   （然后 orchestrator --adapter mock）
"""
from __future__ import annotations

import json
import socketserver
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler

API_PORT = 9900

CHALLENGES = [
    {
        "unique_code": "mock-easy-001",
        "description": "一个简单 Web 服务，首页 HTML 源码里可能直接泄露 flag（flag 形如 flag{...}）。",
        "difficulty": "easy", "level": 1, "total_score": 100.0, "flag_count": 1,
        "flags": ["flag{easy_homepage_local}"], "port": 9901,
    },
    {
        "unique_code": "mock-med-002",
        "description": "一个 Web 服务，robots.txt 可能泄露被禁止的隐藏页面路径。",
        "difficulty": "medium", "level": 3, "total_score": 200.0, "flag_count": 1,
        "flags": ["flag{med_robots_flag}"], "port": 9902,
    },
    {
        "unique_code": "mock-hard-003",
        "description": "一个 API 服务，GET /api/check?id=<n> 只在某个特定 id 下返回 flag。",
        "difficulty": "hard", "level": 5, "total_score": 300.0, "flag_count": 1,
        "flags": ["flag{hard_brute_42}"], "port": 9903,
    },
]

_correct: dict[str, set[str]] = {}
_cumulative: dict[str, float] = {}


def _public(ch: dict) -> dict:
    done = _correct.get(ch["unique_code"], set())
    return {
        "unique_code": ch["unique_code"],
        "description": ch["description"],
        "difficulty": ch["difficulty"],
        "level": ch["level"],
        "total_score": ch["total_score"],
        "flag_count": ch["flag_count"],
        "correct_flag_count": len(done),
        "is_completed": len(done) >= ch["flag_count"],
        "container_status": "available",
        "container_addr": [f"127.0.0.1:{ch['port']}"],
    }


def _find(code: str) -> dict | None:
    for ch in CHALLENGES:
        if ch["unique_code"] == code:
            return ch
    return None


def _submit(code: str, flag: str) -> dict:
    ch = _find(code)
    if not ch:
        return {"correct": False, "awarded": 0, "cumulative_score": 0,
                "correct_flag_count": 0, "total_flag_count": 0,
                "matched_flag_index": None, "code": "challenge_not_found"}
    done = _correct.setdefault(code, set())
    if flag in ch["flags"]:
        first = flag not in done
        done.add(flag)
        awarded = ch["total_score"] / ch["flag_count"] if first else 0.0
        _cumulative[code] = _cumulative.get(code, 0.0) + awarded
        return {"correct": True, "awarded": awarded,
                "cumulative_score": _cumulative[code],
                "correct_flag_count": len(done), "total_flag_count": ch["flag_count"],
                "matched_flag_index": ch["flags"].index(flag)}
    return {"correct": False, "awarded": 0,
            "cumulative_score": _cumulative.get(code, 0.0),
            "correct_flag_count": len(done), "total_flag_count": ch["flag_count"],
            "matched_flag_index": None}


class ApiHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path == "/openapi/v1/challenges":
            self._send([_public(ch) for ch in CHALLENGES])
        else:
            self._send({"code": "not_found", "message": f"no route {path}"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path == "/openapi/v1/challenges/start":
            code = (qs.get("unique_code") or [""])[0]
            ch = _find(code)
            if ch:
                self._send({"container_addr": [f"127.0.0.1:{ch['port']}"]})
            else:
                self._send({"code": "challenge_not_found", "message": "no such"}, 404)
        elif path == "/openapi/v1/challenges/close":
            self._send({"ok": True})
        elif path == "/openapi/v1/challenges/submit":
            body = self._read_json()
            self._send(_submit(body.get("unique_code", ""), body.get("flag", "")))
        else:
            self._send({"code": "not_found", "message": f"no route {path}"}, 404)


class TargetHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _html(self, body: str, code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj: dict, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        port = self.server.server_address[1]
        path = urllib.parse.urlparse(self.path).path
        if port == 9901:
            if path in ("/", "/index.html"):
                self._html("<html><body><h1>欢迎使用审批系统</h1>"
                           "<!-- flag{easy_homepage_local} --></body></html>")
            else:
                self._html("<h1>404</h1>", 404)
        elif port == 9902:
            if path == "/robots.txt":
                self._html("User-agent: *\nDisallow: /secret-page\n")
            elif path == "/secret-page":
                self._html("<html><body><h1>隐藏管理页</h1>"
                           "<p>flag{med_robots_flag}</p></body></html>")
            else:
                self._html("<h1>404</h1>", 404)
        elif port == 9903:
            if path == "/api/check":
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                try:
                    n = int((qs.get("id") or ["0"])[0])
                except ValueError:
                    n = -1
                if n == 42:
                    self._json({"ok": True, "data": "flag{hard_brute_42}"})
                else:
                    self._json({"ok": False, "data": "not found"})
            else:
                self._html("<h1>404</h1>", 404)


def _serve(port: int, handler):
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as s:
        s.serve_forever()


def main():
    threads = [
        threading.Thread(target=_serve, args=(API_PORT, ApiHandler), daemon=True),
        threading.Thread(target=_serve, args=(9901, TargetHandler), daemon=True),
        threading.Thread(target=_serve, args=(9902, TargetHandler), daemon=True),
        threading.Thread(target=_serve, args=(9903, TargetHandler), daemon=True),
    ]
    for t in threads:
        t.start()
    print(f"[mock_bench] TSec API on :{API_PORT}, 靶场 9901/9902/9903 就绪")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[mock_bench] 退出")


if __name__ == "__main__":
    main()
