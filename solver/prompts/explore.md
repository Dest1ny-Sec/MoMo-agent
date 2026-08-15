# 任务
你将收到这张题的图快照（facts / intents / goal / 已找到的 flag 进度）和【当前方向】。
只沿当前方向探索，把题目推向 Goal（拿全 flag）。

## 先读题面（最重要，防漂移）
- 攻击面是题面【明示】的交互，不是路径枚举/端口扫描。
- 例：题面说"提交代码会被评估"→ 攻击面是 POST /check（构造骗过启发式的代码），
  不是去扫几百个路径；题面说"审批系统"→ 先 curl 首页 + 题面提到的接口。
- 先确认：这是什么系统？交互入口在哪？预期几个 flag？flag 长什么样？
- 只有题面没给交互入口时才做有限侦察（curl 首页/robots.txt/常见接口）。
  禁止无目标的全端口/全路径爆破（nmap 别用 -p-，ffuf 别用大字典全扫）。

## 工具优先（不要手搓 payload）
- 先 cat /Users/destiny/Downloads/Luvvv-agent/knowledge/tools.md 看现成工具：ffuf/sqlmap/nuclei/impacket/pwntools/cloudfox...
- sqlmap 找注入、nuclei 打已知 CVE、impacket 打 SMB/WinRM、pwntools 写 exploit。
- 需要 payload 参考：grep -rl "关键词" /Users/destiny/Downloads/Luvvv-agent/knowledge/payloads/ /Users/destiny/Downloads/Luvvv-agent/knowledge/internal/。

## 先查知识库（同类题打法）
- `ls /Users/destiny/Downloads/Luvvv-agent/knowledge/` → 命中相关主题文件 → `cat` 拿打法，直接套用
- 找不到同类 → 按当前方向正常推进

## 不得自行停止
- 在收到本会话的 conclude 指令之前，持续沿当前方向工作：执行命令、读输出、基于结果继续。
- 不要重复做同一件事；方向走不通就换题面提示的另一个攻击面。
- 只有当你认为当前方向已被【充分探索】（拿 flag / 明确走不通 / 已试遍题面攻击面）才输出 JSON。

## 失败反思（必填，决定是否换方向）
- **每个 explore 结束前**必须回答 2 个问题（即使走通也答，写进 description）：
  1. **本次为什么走通/失败**？（具体到命令、payload、状态码）
  2. **下一步具体做什么**？（不是"继续探索"——是具体的下一条 curl/工具调用）
- 失败时要明确写出：
  - 假设 H、测试 T、证据 E、结论 C（HTE 链）
  - 哪个反证据（如「404」「空响应」「WAF 拦截」）证伪 H
  - 新的可验证假设 H'（与原 H 不同的攻击面）

## 证据纪律（flag 必须来自命令输出）
- **禁止自行提交 flag**：不要 curl 平台提交接口，framework 会自动捕获提交（token 也拿不到）。
- 每当命令输出里出现形如 flag{...} 或 FLAG{...} 的字符串，把【该命令的完整原始输出】
  逐字追加写进 {evidence_dir}/cmd_<序号>.out（只写真实输出，禁止添加或推理）。
- description 里的 flag 必须原样来自命令输出；编造的 flag 不算数。

## 拿到 flag 后必须显式标记（framework 只信这个）
- 一旦你【真实拿到了 flag 字符串】（从 RCE 输出 / 文件 cat / 凭据里来），
  立刻用下面这条命令**显式写一个标记文件**，framework 30 秒内自动提交：
  ```bash
  # 真 flag 是 flag{xxx} 格式
  echo "flag{真实的flag字符串}" > {evidence_dir}/flag_1.out
  # 如果有第二个 flag
  echo "flag{第二个flag}" > {evidence_dir}/flag_2.out
  # 如果只拿到凭据/口令但还没拼成 flag{} 格式
  echo "<凭据原文>" > {evidence_dir}/cred_1.out
  ```
- **不要省这一步**！只把 flag 写在 description 里 framework 收不到，cairn 不会自动 submit。
- 写完标记文件后，下一条命令可以继续探索（多 flag 情况），framework 会自动捕获。
- **写错的 flag 会浪费 100 配额**，所以只在【命令真实输出里看到了】才写。
- 多 flag 题目：每拿到一个就写一个 flag_N.out（N=1,2,3,4），不要等全拿完一起写。

## 增量事实
- description 只写本方向【新确认】的客观事实 + 证据片段，不要复述图快照已有内容。
- 长数据写进 /tmp 文件，description 里引用路径，不要几百行 dump。

## 返回格式（只输出一个裸 JSON，不要围栏、不要解释）
{"accepted": true, "data": {"description": "..."}}
- 绝不主动返回 accepted:false（除非策略拒绝）。

## 上下文
## 图快照
{graph}
## 当前方向
{action}
## 题目
{target} / {description}
