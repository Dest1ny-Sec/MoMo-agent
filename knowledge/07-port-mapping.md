# 主题：端口 → 题型预判（来自 Cairn 实战侧信道）

## 场景
看到题目 start 返回的 `container_addr: 10.0.189.x:<port>`，**先看端口再读题面**，能 80% 锁定题型模板，
省去 nmap 端口扫描的 30 秒+ 误判。

## 端口映射表（来自 Cairn proj_007 实战 60+ 题沉淀）

| 端口 | 题型/组件 | 速查打法 |
|---|---|---|
| `:80` | 通用 Web / WAF 系列 / 业务门户 | 抓 Server 头 → 看 Werkzeug? PHP? nginx? 然后按 `01-web-waf-bypass.md` / `04-file-read.md` 套路 |
| `:8080` | Python 编辑器 / 图数据库 / GeoServer | 看 Web 标题/图标；Gremlin 看 CVE-2024-27348；GeoServer 走 OGC 协议探测 |
| `:8000` | Python 沙箱 / 云题 / 报表服务 | Flask/Werkzeug = Python 应用，**优先** `/debug/config`、`/console`、`.git` |
| `:23` | telnet 明文登录 | 直接 nc 试弱口令 + banner 抓版本 |
| `:22` + `:10086` | 1Panel 面板 | 默认 1Panel 入口在 10086；看是否需要 EntranceCode + 验证码 |
| `:8188` | **ComfyUI**（AI 推理） | 走 :8188 前端；历史 RCE/未授权接口；POST `/prompt`/queue 探测 |
| `:7860` | **Gradio**（AI 演示/工作流） | 走 `/config` `/info` 探；4.12.0 有已知未授权文件读 |
| `:3000` | **Dify**（AI 应用平台） | 走 `/api` 探未授权；SSTI 风险；插件上传 |
| `:8443` | OFBiz / 通用 HTTPS | 跳过证书校验看 banner；OFBiz 走 `webtools/control/ViewHistory` |
| `:5005` | GeoServer 管理 | 走 `/web/` 探 |
| `:10000` | 云门户（Webmin/相似）| 走 `/` 探默认口令 |
| `:9004-:9014` | **f1 二进制 TCP 行协议** | 端口号一般对应题号；nc 连发指令、看 banner 找协议握手 |
| `:9101-:9108` | **f2 固件逆向 / IoT** | 端口号对应题号；一般 9101=f2-01；走 fuzzer + pwntools |
| 内网 `:5000` | internal-api | a-16 实测有 `/debug/config` 泄 admin_token |

## 决策树（开局 5 秒判断）

```
看到 start 返回 :port
  ↓
是 :80 / :8080 / :8000 之一？
  ├─ 是 → Web 题 → cat /opt/tools.md + 看 Server 头 → 按 01/02/04 套路
  └─ 否 → 看 :port 是不是 8188 / 7860 / 3000 / 8443？
       ├─ 是 → AI 组件题 → 用对应 CVE 工具
       └─ 否 → 看是不是 9xxx？
            ├─ 9xxx → f1/f2 二进制题 → 用 pwntools/逆向
            └─ 其它 → nmap 大范围扫同 IP 邻居端口
```

## 关键提醒

- **同题实例地址会漂移**（.24 ↔ .25 ↔ .26），但**端口后缀稳定**——不要根据 IP 判断题型
- **:8188 + :7860 + :3000 是 AI 题的金标准**，看到任一直接走 CVE 工具不要从零开始
- **不要做全端口扫描**（`nmap -p-` 太慢且不必要）；先看 start 返回的端口查这张表
- f1/f2 的端口号本身带题号信息（9101 = f2-01），可作为提交策略 hint
