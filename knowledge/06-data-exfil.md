# 主题：数据外传通道（DNS 隧道 / 分块传输 / 组装检索）

## 场景
需把内容经隧道外传（DNS 通道 / 分块 POST / 组装后检索）。

## 通用流程
1. **发现通道**：`/dns`、`/tunnel`、`/exfil`、`/upload` 等端点；POST 数据到 `<块数据>.<channel>.<domain>`
2. **分块编码**：内容切固定大小块（如 32B），每块编码（base32/base64）+ 序号：
   `格式: <seq>-<total>-<encoded>.<channel>.challenge.local`
3. **逐块发送**：保持同一会话（session id / cookie）
4. **组装检索**：`GET /retrieve?session=<id>` → `{"assembled_size": N, "complete": true, "flag": "FLAG"}`

## 关键点
- **保持会话**：块发送和 retrieve 用同一 session，否则组装失败
- **块格式**：先读接口文档或试一两个块看响应，确认 seq/total/编码格式
- **完整发送后才 retrieve**：`complete: true` 才是组装完成
- flag 从 retrieve 响应里逐字抓取存档

## 工具
- `curl -X POST /dns` 逐块；脚本循环发 N 块
- base32/base64：`python3 -c "import base64; ..."`
