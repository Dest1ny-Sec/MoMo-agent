# 主题：任意文件读取（LFI / 路径穿越）

## 场景
下载 / 查看 / 预览功能存在未过滤的文件路径参数（`id` `file` `path` `filename`），拼接后直接读取。

## 识别与利用
- 找下载/查看接口：`download.php?id=FILE`、`file=`、`path=`、`preview=`
- 路径穿越：`id=../secret.php`、`id=../../../../etc/passwd`
- 读到 `/etc/passwd` 即确认任意文件读

## LFI 的价值
- **读全部源码** → 找硬编码账号、敏感数据、隐藏端点、注释线索
- 源码注释常泄露题面线索（如「临时开放接口 / TODO: 加回权限校验」）
- 读 `.htaccess`/配置 → 了解被 Apache 拦的文件（`Deny (config|auth)\.php$`），这些往往是敏感端点，但注意它**不拦 /api/ 下的文件**
- 读 `Dockerfile` / 部署脚本 → 了解应用结构与 flag 落点

## 常见源码敏感点
- `config.php`：硬编码账号 `$USERS`、目录常量、敏感数据清单
- 路由分发 `index.php`：switch/路由表 → 全部端点
- 认证 `auth.php`：权限校验逻辑 → 找绕过

## flag 定位方法论（拿到任意读后）
1. 常见文件：`/flag` `/flag.txt` `/root/flag*` `/tmp/flag*`、web 根、`/etc/passwd` 里的用户名线索
2. `/proc/mounts`：找 `ro` bind mount 的 flag 文件
3. `env`：环境变量
4. **诱饵陷阱**：读到的 flag 提交被拒（correct:false）→ 换位置继续找
5. 配置/日志/备份：`*.sql`、`*.bak`、`README*`、`config.*`

## LFI → 源码 → 隐藏能力（进阶）
1. 用 LFI 读全量源码 → 找 **API key / 硬编码凭据**（常藏在 `settings.py`/`config.php`，注释常提示「WARNING: 含敏感凭据」）
2. 用 API key 调用**受保护接口**（如转换/管理 API，之前返回 Invalid API Key）
3. 从源码找**内部服务地址**（如 `converter:5001`）→ 直连内部端口探测（SSRF 或直接访问）
4. 题面线索"可疑日志/异常调用"→ 定位日志文件与审计端点

## 已知实现 PoC 检索
- 非通用自定义服务，先确认是否命中**已知开源实现**：在本地模板/PoC 目录 `grep -ril "服务名|协议名"`（nuclei-templates、vulhub、本地 pocs）
- 命中已知实现 → 直接套已知漏洞/CVE payload，别重新造轮子

## 工具
- `curl "http://T/preview?file=../../../../etc/passwd"`（路径穿越）
- ffuf 枚举端点；LFI 文件存在性批量探测
