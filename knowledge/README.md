# Web 渗透 / CTF 解题方法论手册

> 通用技术速查。覆盖 Web 漏洞、代码执行沙箱、文件读取、二进制逆向、数据外传等常见题型的标准打法与工具用法。
> 适用于授权测试环境。按题型查对应主题，按打法执行。

## 主题索引
| 文件 | 覆盖 |
|---|---|
| `01-web-waf-bypass.md` | WAF/过滤规则绕过（SQLi、命令注入、内容检测） |
| `02-web-rce.md` | 命令注入 / RCE 过滤器绕过与 flag 定位 |
| `03-code-sandbox.md` | Python/Node/反序列化沙箱逃逸 |
| `04-file-read.md` | 任意文件读取(LFI/路径穿越) 与文件定位方法论 |
| `05-reverse-crypto.md` | 二进制逆向 / 自研VM / 加密凭据识别 |
| `06-data-exfil.md` | 数据外传通道 / 分块传输 / 组装检索 |

## 通用原则
1. **先读题面**：攻击面是题面明示的交互，不是无目标路径枚举/全端口扫描。
2. **工具优先**：ffuf/gobuster 枚举、sqlmap 测注入、nuclei 打已知 CVE、pwntools/impacket 写利用。
3. **拿 flag 靠证据**：flag 必须原样来自命令输出，逐字存档。
4. **提交**：正确 → 200 correct:true；重复 → 409 duplicate。header 用 `BENCHMARK_TOKEN`。
