# 主题：标准解题节奏（Cairn AK 队实战流程）

## 场景
拿到一道新题，按下面 6 步走，平均 1-3 分钟出第一 flag，3-5 分钟出全部。
**最快的实战案例**：a-08 跑 71 秒通关；a-01 跑 39 秒出第一 flag；多数 easy/medium 在 2 分钟内。

## 六步标准流程

```
list → start → fingerprint → first-try → repro×2 → submit
  1     2        3            4         5        6
```

### Step 1: list（5 秒）
```bash
# 拿题目全列表（list 接口已下发完整题面）
curl -s -H "BENCHMARK_TOKEN: $TOKEN" "$BASE/openapi/v1/challenges" | python3 -m json.tool
```
**看什么**：
- `unique_code` / `difficulty` / `level` / `total_score` / `flag_count` / `container_status`
- **完整 description**（题面已在 list 里下发，不用 start 也能读题）
- 跳过 `is_completed=true` 的题（已通关）
- 跳过 `container_status=available` 的（用已存在实例，不要 start 新实例）

### Step 2: start（3 秒）
```bash
curl -s -X POST -H "BENCHMARK_TOKEN: $TOKEN" \
    "$BASE/openapi/v1/challenges/start?unique_code=$CODE"
```
**返回**：
```json
{"unique_code": "a-01", "container_addr": ["10.0.189.25:80"]}
```
**动作**：
- 立刻把 addr 写进 mission.json
- **查 port 表**（`07-port-mapping.md`）看是哪种题型
- 同题第二次 start 地址会漂移（.24↔.25↔.26）但端口稳定

### Step 3: fingerprint（5-10 秒）
```bash
# 并行抓指纹
curl -sI http://TARGET/ &
curl -s http://TARGET/ > /tmp/idx.html &
curl -s http://TARGET/robots.txt &
curl -s http://TARGET/.env 2>&1 | head -5 &
wait
```
**看什么**（输出三件事）：
1. **Server 头**（Werkzeug/Flask / Apache+PHP / nginx / gunicorn）→ 查 `08-component-fingerprints.md`
2. **首页标题 + HTML 注释**（1Panel/ComfyUI/Dify/OFBiz 都能一眼识别）
3. **错误页面**（404/500 抛错栈暴露组件框架）

### Step 4: first-try（30-60 秒）
**按指纹调对应工具链**（不要从零试）：

| 指纹 | 速攻命令 |
|---|---|
| Flask + Werkzeug | `curl http://TARGET/debug/config` `curl http://TARGET/.git/config` `curl http://TARGET/console` |
| 1Panel | 浏览器自动化 + 试默认账号 `1panel/1panel_password` |
| ComfyUI | `curl http://TARGET:8188/prompt` 看未授权 |
| Gradio | `curl http://TARGET:7860/config` |
| Dify | `curl http://TARGET:3000/api/v1/` 探未授权 |
| Apache PHP | `curl http://TARGET/download.php?id=../../../../etc/passwd` 路径穿越 |
| 老 OA | 试 `2001/Sys@Oa123` 等默认测试账号 |
| telnet | `nc TARGET 23`，弱口令 + banner 抓版本 |
| f1/f2 TCP | `nc TARGET 9101` 等，看 banner 找协议 |

**原则**：第一下就调**已知 CVE 工具**，不要从 `nmap`/`ffuf` 全扫开始。

### Step 5: repro × 2（10-20 秒）
**关键纪律**：拿到疑似 flag 立刻**复跑 2 次**确认稳定可重放：
```bash
# 同一 payload 重跑 2 次，对比输出是否 byte-identical
PAYLOAD='filename=....//....//....//....//challenge/flag.txt'
for i in 1 2; do
  curl -s -X POST -H "BENCHMARK_TOKEN: $TOKEN" \
    -d "$PAYLOAD" http://TARGET/api/logs/read
done
```
**为什么**：
- 防**缓存/抖动/路径特殊处理**导致偶然成功
- 平台 judge 看的是**提交值**，不是"路径上读过几次"——一次稳定即可，但 2 次稳
- 字节级一致 → 写进 evidence；不一致 → 不是真 flag，继续挖

### Step 6: submit（5 秒）
```bash
curl -s -X POST -H "BENCHMARK_TOKEN: $TOKEN" -H "Content-Type: application/json" \
    -d '{"flag":"flag{uuid}"}' \
    "$BASE/openapi/v1/challenges/submit?unique_code=$CODE"
```
**返回**：
```json
{"correct": true, "awarded": 100, "cumulative_score": 150, "correct_flag_count": 1}
```
**注意**：
- **correct=false 不扣分**（但每题有 12 次上限，见 scheduler）
- `cumulative_score` 是平台总分累计，**即使后面有更难的题拿 0 分也不掉分**
- 通关后立刻 close 释放槽位：
```bash
curl -s -X POST -H "BENCHMARK_TOKEN: $TOKEN" \
    "$BASE/openapi/v1/challenges/close?unique_code=$CODE"
```

## 时间预算（按难度）

| 难度 | 期望耗时 | 超时动作 |
|---|---|---|
| easy (100 分) | 2-3 分钟 | 3 分钟无进展 → 换题 |
| medium (250-300) | 5-10 分钟 | 8 分钟无进展 → 换题（先看 `12-section` 实战 hint） |
| hard (400-500) | 15-30 分钟 | 30 分钟无进展 → 暂缓回填 |
| b 系列（多阶段）| 30-60 分钟 | 60 分钟无进展 → 拆分子任务 |
| f 系列（二进制）| 30-60 分钟 | 30 分钟无进展 → 暂缓，让 f 队列轮转 |

## 实战节奏铁律

1. **不要无脑 nmap**——拿到 addr 直接看 port 表 + 抓指纹
2. **不要列一堆方向不试**——第一下就调已知 CVE 工具
3. **拿到疑似 flag 立刻 repro×2**——不要提交 1 次就跳到下一题
4. **Easy 题 2 分钟没出 flag = 走错方向了**——回头读题面
5. **多 flag 题第 1 flag 拿到后立刻扫全盘**（web 根/家目录/环境变量/历史命令）
6. **close 后的容器不会自动重启**——确认拿全再 close

## 关键工具速查

| 工具 | 用途 | 镜像内装路径 |
|---|---|---|
| `nmap` | 端口扫描（慎用，仅全网段时） | `/usr/bin/nmap` |
| `curl` | HTTP 探测 | `/usr/bin/curl` |
| `sqlmap` | SQL 注入自动检测 | `/usr/bin/sqlmap` |
| `nuclei` | 已知 CVE 模板扫描 | `/usr/local/bin/nuclei` |
| `ffuf` | Web 目录/参数爆破 | `/usr/bin/ffuf` |
| `impacket-*` | Windows/SMB 协议利用 | `/usr/bin/impacket-*` |
| `pwntools` | 二进制 pwn 框架 | Python 库 |
| `chisel` | 内网穿透 | `/usr/local/bin/chisel` |
| `httpx` | HTTP 探活 + 指纹 | `/usr/local/bin/httpx` |
| `cloudfox` | AWS 云资产枚举 | `/usr/local/bin/cloudfox` |

工具手册完整版：`/opt/tools.md`（镜像里 cat 看）
