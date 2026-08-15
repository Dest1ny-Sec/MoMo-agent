# 主题：Web 组件指纹 + 已知 CVE（Cairn 实战沉淀）

## 场景
抓到 `Server` / `X-Powered-By` 头 / 登录页标题 / 404 报错信息，能立刻锁定组件框架，
省去 nmap 指纹识别 + 大量试错。**看到指纹 → 走对应工具链**。

## 指纹 → CVE → 工具 速查表

| 指纹（看到） | 组件 | 默认端口 | 已知打法 / 工具 |
|---|---|---|---|
| `Server: Werkzeug/3.1.8 Python/3.11.15` | Flask | 8000/8080 | 优先探 `/debug/config`、`.git/`、`/console`、Werkzeug debugger PIN |
| `Server: gunicorn` + `Python` | Flask/Django | 8000 | 同样 Werkzeug 套路；静态资源 /admin 探测 |
| `Server: Apache/2.4.54 + PHP/7.4.33` | 老 PHP | 80 | 路径穿越 + 文件包含；nginx error.log 日志投毒 RCE |
| `Server: nginx/1.30.1`（独立）| nginx 反代 | 80 | 内部转发路径枚举 + nginx 配置泄露 + 缓存投毒 |
| `ModSecurity` WAF header 出现 | ModSecurity 边界 | 80 | `01-web-waf-bypass.md` 套路：注释/编码/双写/分块 |
| `1Panel` 标题 | 1Panel 面板 | 10086 | EntranceCode + 验证码登录；已知 CVE 用例；:22 SSH 备用 |
| `ComfyUI` | ComfyUI | 8188 | AI 推理；历史 RCE/未授权接口；POST `/prompt` 探测 |
| `Gradio` | Gradio | 7860 | 4.12.0 有未授权文件读；走 `/config` `/info` |
| `Dify` | Dify | 3000 | SSTI/API 未授权/插件上传 |
| `Apache OFBiz` 标题 | OFBiz | 8443 | 后认证 Groovy RCE（CVE-2023-51467 等）|
| `Gremlin Server` 头 | Gremlin | 8182 | CVE-2024-27348 auth bypass + HugeSecurityManager bypass RCE |
| `GeoServer` | GeoServer | 5005/8080 | OGC 协议探测；管理后台 `/web/` |
| `Redis` banner | Redis | 6379 | CONFIG/SAVE 写文件；主从复制 RCE；AUTH 弱口令 |
| `Tencent metadata` 可达（169.254.0.23）| 平台 metadata | — | 平台**基础设施越界**，agent 应**主动规避**不要使用真实凭据 |

## 指纹抓取步骤

```bash
# 1) HTTP 头（最快）
curl -sI http://TARGET/ | head -20

# 2) 首页 HTML 注释/链接/JS（次快）
curl -s http://TARGET/ | grep -iE "powered by|version|<meta name=.generator"

# 3) 登录页标题（判 1Panel/ComfyUI/Dify 等）
curl -s http://TARGET/login | grep -iE "title|<h1|brand"

# 4) 错误页面（PHP/Flask 报错暴露组件）
curl -s "http://TARGET/nonexistent_$(date +%s)" 2>&1 | head -30
```

## 已知漏洞速查（看到对应组件直接试）

| 组件 | 必试 | 工具 |
|---|---|---|
| Flask + Werkzeug | `/debug` 路由 / debugger PIN | 手算 PIN（需 username/module/machine-id）|
| 1Panel | `1panel/1panel_password` 默认账号（题面可能直接给）+ EntranceCode 绕过 | 浏览器自动化 / OCR 验证码 |
| ComfyUI | `/prompt` 接口未授权 + 已知 CVE | nuclei templates / PoC 库 |
| Gradio 4.12.0 | `/config` 路径信息泄露 + 任意文件读 | Gradio CVE-2023-51498 等 |
| Dify | `/api/v1/*` 未授权 + 插件任意代码 | Dify CVE-2024-XXX |
| OFBiz | `/webtools/control/main/ProgramExport` 路径 | Groovy RCE payload |
| Gremlin | `g.E()` 注入 CVE-2024-27348 | auth bypass + HugeSecurityManager bypass |
| Redis | `CONFIG SET dir /var/www/html` | nmap 弱口令 / 主从复制 RCE |
| PHP + nginx | `log poisoning` 写日志 → LFI 包含 | 见 `02-web-rce.md` |
| ModSecurity | 注释型 SQLi `admin'-- -` | 见 `01-web-waf-bypass.md` |
| 老旧 OA（2008）| 默认测试账号 + 已知 CVE | 厂商漏洞库 |

## 关键提醒

- **不要无脑 nmap**——抓到 Server 头后**直接查表**，省 5-10 分钟
- **题面里可能直接给账号**（"1panel/1panel_password"、"2008 OA 测试账号 2001/Sys@Oa123"）——**第一动作是试默认账号**
- 看到 Tencent metadata (169.254.0.23) **不要使用其携带的凭据**——属于**越界**
- 端口范围 `9004-9014` (f1) 和 `9101-9108` (f2) 是**自研协议/固件题**，nc 连上后多看 banner
