"""LLM 工具 schema 定义：bail + 5 个结构化渗透工具（ffuf/sqlmap/nuclei/nmap/hydra/cloudfox）。

从原 llm.py 抽出 BASH_TOOL / _PT / PENTEST_TOOLS / get_tool_command。

工具设计（学 desredteam：把工具注册成 schema，AI 选工具填参数，不是靠提示词碰运气）。
每个工具：name / description / input_schema / build(cmd) —— build 把参数拼成真实命令。
"""
from __future__ import annotations

import logging

LOG = logging.getLogger("solver.llm.tools")

BASH_TOOL = {
    "name": "bash",
    "description": "在目标环境执行一条 bash 命令并返回输出。用于侦察、漏洞利用、读文件、枚举等。",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "要执行的 bash 命令"}},
        "required": ["command"],
    },
}

# ===== 结构化渗透工具 =====
_PT = {
    "ffuf": {
        "description": "Web 目录/参数爆破（比手写 for 循环快得多）。url 用 FUZZ 占位。",
        "schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL，用 FUZZ 占位，如 http://TARGET/FUZZ"},
                "wordlist": {"type": "string", "description": "字典路径", "default": "/usr/share/wordlists/dirb/common.txt"},
                "match_codes": {"type": "string", "description": "匹配状态码，逗号分隔", "default": "200,204,301,302,307,401,403"},
                "threads": {"type": "integer", "description": "线程数", "default": 50},
            },
            "required": ["url"],
        },
        "build": lambda a: f"ffuf -u {a['url']} -w {a.get('wordlist', '/usr/share/wordlists/dirb/common.txt')} -mc {a.get('match_codes', '200,204,301,302,307,401,403')} -t {a.get('threads', 50)} -s",
    },
    "sqlmap": {
        "description": "SQL 注入自动检测与利用。确认注入点后用。",
        "schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "带注入点的 URL"},
                "data": {"type": "string", "description": "POST 数据（可选）"},
                "level": {"type": "integer", "description": "检测等级 1-3", "default": 2},
                "dump_tables": {"type": "boolean", "description": "是否枚举表/数据", "default": False},
            },
            "required": ["url"],
        },
        "build": lambda a: f"sqlmap -u {a['url']} --batch {'--data=' + a['data'] if a.get('data') else ''} --level {a.get('level', 2)} {'--dump' if a.get('dump_tables') else ''}".replace("  ", " "),
    },
    "nuclei": {
        "description": "已知漏洞模板扫描（覆盖大量 CVE/PoC）。",
        "schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL"},
                "tags": {"type": "string", "description": "按标签过滤，如 rce,weaver", "default": ""},
            },
            "required": ["url"],
        },
        "build": lambda a: f"nuclei -u {a['url']} {'-tags ' + a['tags'] if a.get('tags') else ''} -silent".replace("  ", " "),
    },
    "nmap": {
        "description": "端口/服务扫描。",
        "schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "目标 IP/主机"},
                "ports": {"type": "string", "description": "端口范围，如 1-1000", "default": "1-1000"},
            },
            "required": ["host"],
        },
        "build": lambda a: f"nmap -sV -p {a.get('ports', '1-1000')} -T4 {a['host']}",
    },
    "hydra": {
        "description": "在线口令爆破（SSH/FTP/HTTP 等）。",
        "schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "目标"},
                "service": {"type": "string", "description": "服务，如 ssh/http-post-form/ftp"},
                "username": {"type": "string", "description": "用户名"},
                "password_list": {"type": "string", "description": "口令字典路径", "default": "/tmp/pw.txt"},
            },
            "required": ["host", "service", "username"],
        },
        "build": lambda a: f"hydra -l {a['username']} -P {a.get('password_list', '/tmp/pw.txt')} {a['host']} {a['service']} -t 4",
    },
    "cloudfox": {
        "description": "AWS 云资产枚举（S3/EC2/IAM 权限）。",
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string", "description": "AWS profile", "default": "default"},
            },
            "required": [],
        },
        "build": lambda a: "cloudfox aws --profile default enum",
    },
}

PENTEST_TOOLS = [
    {"name": name, "description": spec["description"], "input_schema": spec["schema"]}
    for name, spec in _PT.items()
]


def get_tool_command(tname: str, args: dict) -> str:
    """把 AI 调的工具名+参数 → 真实 shell 命令。

    bash 工具：直接用 args.command。
    其它结构化工具：_PT[name].build(args) 拼命令。
    未知工具：返回占位 echo。
    """
    if tname == "bash":
        return args.get("command", "")
    spec = _PT.get(tname)
    if spec and "build" in spec:
        try:
            return spec["build"](args)
        except Exception as exc:
            return f"echo 参数错误({tname}): {exc}"
    return f"echo 未知工具 {tname}"
