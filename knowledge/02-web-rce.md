# 主题：命令执行 / RCE（过滤器绕过 + flag 定位）

## 场景
诊断面板 / 检测功能 / 提交内容被服务端执行 / 入口有自定义过滤规则。

## 定位执行点
- 找命令执行参数：`cmd` `command` `ping` `check` `execute` `shell` 等
- 后端常见 `shell_exec`/`system`/`exec`/`passthru`（PHP）、`os.system`/`subprocess`（Python）、`exec`/`child_process`（Node）

## 过滤器绕过
- 命令名插反斜杠：`c\at /path/f\lag1.txt`（绕过 `\b` 黑名单）
- 分隔符/变量：`;` `|` `&&` `${IFS}` `$()` 反引号 `%0a`
- 全路径：`/usr/bin/cat`、`/bin/cat`
- 编码：URL 双重编码、`$'...'` ANSI-C 引号

## 拿 flag（RCE 后优先级）
1. **全盘找 flag 文件**：
   - `find / -name "*flag*" 2>/dev/null`
   - `ls -la / /root /tmp /var/www /opt /srv /home 2>/dev/null`
   - 常见：`/flag` `/flag.txt` `/root/flag*` `/tmp/flag*`、web 根、挂载点
2. **检查 bind mount**：`cat /proc/mounts`（`ro` 挂载的 flag 文件）
3. **环境变量**：`env`（flag 可能在环境变量里）
4. **诱饵陷阱**：读到的某个 flag 提交被拒（correct:false）→ 可能是诱饵，继续找真实 flag（换位置/看挂载/找备份）
5. 无回显 → `curl` 外带 / `sleep` 时间盲注 / DNS 外带

## 提示
- 每次命令输出含 flag 都要逐字存档（证据）
- 文件读不到时检查权限，必要时提权（SUID、sudo 配置、内核 EXP）
