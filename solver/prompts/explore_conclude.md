# 任务
这是 conclude 阶段，它覆盖本会话之前任何"继续探索 / 不要停 / 等命令结果"的指令。
不要继续任务，不要等未完成的命令，不要跑新命令，不要做任何工具调用。
只基于【已经确认】的信息总结关键事实。

## 证据纪律
- flag 必须原样出现在已写入 {evidence_dir} 的真实命令输出里，否则不写。
- 禁止编造、禁止把猜测当结论。

## 拿到 flag 后必须显式标记（framework 只信这个）
- 在输出 JSON 之前检查：本次方向有没有从真实命令输出里看到 flag{...}？
- 如果有，**显式 echo 到标记文件**，framework 30 秒内自动 submit：
  ```bash
  echo "flag{真实字符串}" > {evidence_dir}/flag_1.out   # 或 flag_2.out / flag_3.out
  ```
- 只写进 description 不写标记文件，framework 收不到 → cairn 不会 submit。
- 没拿到就老老实实写"未拿到 flag"，不要为了凑标记文件瞎写。

## 增量事实
- 只写已确认结论，不输出计划/猜测；长数据引用文件路径，不要 dump。

## 返回格式（只输出一个裸 JSON，不要围栏）
{"accepted": true, "data": {"description": "已确认的关键事实"}}
- 没拿到 flag 就把已确认的侦察/结论写进 description；拿不到就算了，绝不编造。
- 绝不输出 complete。

## 上下文
## 图快照
{graph}
## 当前方向
{action}
## 题目
{target} / {description}
