# Changelog

## 索引

| 版本 | 日期 | 摘要 |
|---|---|---|
| v0.1.0 | 2026-08-15 | 首次公开：自主安全评估 Agent（CTF/漏洞评估） |

## 项目结构

```
MoMo-agent/
├── orchestrator/   # 主调度（bootstrap / reason / explore 三阶段）
├── solver/         # 单题解题循环
├── adapters/       # 靶场适配器（CTFd / 本地 Docker / 自定义）
├── knowledge/      # RAG 知识库
├── frontend/       # Vue3 实时面板
└── scripts/        # 启动脚本
```

## 核心思路

**两轮制 + 状态空间搜索**：
- 第 1 轮：每题 ≤ 20 分钟
- 第 2 轮：未解出的题目重试
- 状态空间：`origin → intent → fact → goal` 黑板搜索
