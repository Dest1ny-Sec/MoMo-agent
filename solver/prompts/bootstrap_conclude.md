# 任务
这是 conclude 阶段，它覆盖本会话之前任何"继续探索 / 不要停 / 等命令结果"的指令。
不要继续任务，不要等未完成的命令，不要跑新命令，不要做任何工具调用。
只基于【已经确认】的信息总结关键事实。

## 证据纪律
- flag 必须原样出现在已写入 {evidence_dir} 的真实命令输出里，否则不写。
- 禁止编造、禁止把猜测当结论。

## 返回格式（只输出一个裸 JSON，不要围栏）
{"accepted": true, "data": {"fact": {"description": "已确认的关键结果"}}}
- 不要输出 complete 键（即使没达成 Goal 也写进 fact.description）。

## 上下文
## 图快照
{graph}
## 题目
{target} / {description}。预期 {flag_count} 个 flag。
