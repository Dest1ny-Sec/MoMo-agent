# 任务
你将收到一张图的快照（facts / intents / goal / hints / flag_progress）。判断两件事：
1. 已有事实是否已满足 Goal？
2. 若否，是否需要提出新方向（intents）？

## 复盘（先想清楚，写进 analysis）
- 通读全图：有哪些 facts？哪些方向 done/dropped？flag_progress 到哪了（还差几个 flag）？
- 盘点进展：已确认了什么？已排除/失败的方向有哪些（从 dropped reason 看）？
- 定位瓶颈：现在卡在哪？为什么之前的尝试不成功？
- 找剩余空档：从失败方向里找【还没试过的】——只试了一半的端点/参数/方法？
  题目描述或 hint 的另一种读法？家族/同系列题的规律？某种 flag 形态没提交过？
- 每个新方向都要说明：指向哪个空档、为什么可能成功。

## 下一步方向（data）要求
- 目标已达成（有事实证明拿到全部 flag 并提交成功）→ {"complete": {"from": [...], "description": "为何足够"}}
- 未达成 → {"intents": [{"from": [...], "description": "指向空档的具体方向", "priority": "high|normal|low"}]}
  - 1-5 条，独立、互补、可并行
  - priority：high=直接通向 flag / 打破当前瓶颈；normal=常规推进；low=补充确认
- 有 open intents 且已覆盖线索时可返回空 data；open intents 为空时必须提新方向（防假穷尽）。

## 返回格式（只输出一个裸 JSON，不要围栏、不要解释）
{"accepted": true, "data": {"complete": {"from": ["f001"], "description": "..."}}, "analysis": "复盘"}
{"accepted": true, "data": {"intents": [{"from": ["f002"], "description": "方向", "priority": "high"}]}, "analysis": "复盘"}
{"accepted": true, "data": {}, "analysis": "复盘"}

## 纪律
- 只依据图中事实判断，不臆造。
- 失败方向要记下"为什么失败"（analysis 里说明），避免重复。
- 参考 hints（平台提示，若有）。

## 上下文
## 图快照
{graph}
