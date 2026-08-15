# 工具配置（2026-08-12 装好的工具清单）

## 已装工具（solver 启动时跑这段就发现）

### 漏洞搜索类
- **searchsploit** — `/opt/homebrew/bin/searchsploit`（exploitdb，47,411 个 exploit）
  - 已知组件 → 直接搜：`searchsploit thinkphp 5.0` `searchsploit --cve 2021-44228`
  - 拿到 EDB-ID → `searchsploit -m <id>` 复制 PoC 跑
- **nuclei** — `/usr/local/bin/nuclei` (v3.4.7)
  - 模板目录：`/Users/destiny/.local/nuclei-templates/`（git clone projectdiscovery/nuclei-templates，13,906 文件，17 类）
  - 用法：`nuclei -t <template-dir> -u <target> [-severity high,critical]`
  - 模板分类：`http/cves/ http/exposures/ http/default-logins/ http/technologies/ http/vulnerabilities/`
  - 高速扫描 + 极低误报，是 PoC 工具第一选择
- **vulhub-pocs** — `/Users/destiny/.local/vulhub-pocs/`（158 个 CVE 漏洞环境）
  - 看具体 CVE 的 exploit 利用方式：参考 `README.md` 或 `docker-compose.yml`
  - 不是直接用，是参考 PoC 代码

### 探测类
- **httpx** — `/opt/homebrew/bin/httpx`
  - 批量探测：`cat targets.txt | httpx -status-code -title -tech-detect`
  - 单个：`echo http://10.0.175.24 | httpx -status-code -title -server`
- **nmap** — 系统自带
  - 限制使用：**不要 `-p-`**，只对题面提示的端口 + 关键端口（80/443/8080/8443/5005/1099/2375/9200/6379）
  - 服务识别：`nmap -sV -p 80,8080 <target>`
- **curl** — 系统自带（最常用，先 curl 再上工具）

### whatweb（⚠️ 装上但跑不了）
- `/Users/destiny/.local/whatweb/whatweb` — ruby 2.6 装不上 addressable gem
- 替代：httpx `-tech-detect` / 直接看 Server 头

## 知识库（必读）

### 1) 9 份主题文档（按场景）
- `01-web-waf-bypass.md` — WAF 绕过
- `02-web-rce.md` — Web RCE 套路
- `03-code-sandbox.md` — Python sandbox 逃逸
- `04-file-read.md` — 文件读取漏洞
- `05-reverse-crypto.md` — 逆向 + 密码
- `06-data-exfil.md` — 数据外传
- `07-port-mapping.md` — 端口→组件映射
- `08-component-fingerprints.md` — Server 头→组件
- `09-playbook.md` — 6 步节奏
- `10-framework-issues.md` — 框架问题清单（本次写的）

### 2) 公开 PoC 库
- **PayloadsAllTheThings**（git clone 失败，路径在 prompt 中已改）
- **InternalAllTheThings**（同上）
- **vulhub** — 本地 `/Users/destiny/.local/vulhub-pocs/`

## 工具使用纪律（强约束）

1. **禁止 `nmap -p-`**（题目说"不要大规模端口扫描"）
2. **禁止 `ffuf` 大字典全扫**（用 knowledge/07-port-mapping.md 的常见端点表 + 单个 curl）
3. **禁止自写 fuzz 脚本**（除非必要 LFI/RCE 路径）
4. **必须 Tool Discovery** — 第 1 步先跑这段发现工具：
   ```bash
   which searchsploit nuclei httpx 2>/dev/null
   ls /Users/destiny/.local/nuclei-templates/http/cves/ 2>/dev/null | head -10
   ls /Users/destiny/.local/vulhub-pocs/ | grep -i <component> 2>/dev/null
   ```
5. **Component-First**：拿到 Server 头 → 查 `08-component-fingerprints.md` → 命中 → `searchsploit <component> <ver>` → `nuclei -t ... -u <target>`

## 测试用例

```bash
# 探测单端口
echo http://10.0.175.25:8000/ | httpx -status-code -title -server

# nuclei 打 CVE
nuclei -t /Users/destiny/.local/nuclei-templates/http/cves/ -u http://10.0.175.25:8000/ -severity high,critical

# searchsploit 找 PoC
searchsploit thinkphp 5.0

# exploit-db 复制
searchsploit -m 12345
```
