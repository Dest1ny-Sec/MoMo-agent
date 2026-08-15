# 框架问题清单（2026-08-12 排雷）

## 已修（本次）

### 1. prompt 路径是容器路径，solver 跑在宿主机
- **症状**：solver 看不到 `/opt/ctf-knowledge/09-playbook.md`、`/opt/tools.md`、`/opt/PayloadsAllTheThings/`
- **根因**：prompt 模板硬编码 `/opt/...`，但 solver 实际跑在宿主机 `/Users/destiny/Downloads/Luvvv-agent/`
- **修法**：bootstrap.md / explore.md 等所有 prompt 改用 `/Users/destiny/Downloads/Luvvv-agent/knowledge/...`
- **影响**：b-01 自己读了 knowledge（它会 grep 真实路径），b-02/b-03 不读（因为路径不存在）

### 2. solver.log buffering
- **症状**：solver 跑了 5 分钟但 solver.log 只有 1 行（bootstrap 启动时间）
- **根因**：subprocess.Popen `stdout=open(file, "a")` 默认 buffered（4096 字节）
- **修法**：Popen 加 `bufsize=0` 失败，改用 `buffering=1`（line-buffered）+ `python -u` flag

### 3. evidence 写完没 notify
- **症状**：cairn 不知道 solver 已写完 evidence，无法提前判断进度
- **修法**：`_report_flags` 写完 flags_found.jsonl 后 touch `flags.notify`，cairn 未来可监听

### 4. worker=claude 套壳 deepseek
- **症状**：每次 round 启动 claude CLI 二进制（1-2s）+ deepseek-v4-flash 协议转换
- **根因**：settings.json 把 ANTHROPIC_BASE_URL 改到 deepseek，但走 claude CLI 套壳层
- **修法**：config.json 改 `worker: "llm"`（走 LLMClient.agentic 直连），build_worker 返 None 时走 api 直连
- **效果**：省 1-2s/round + 少一层协议转换

### 5. explore 失败没反思
- **症状**：explore 失败直接 drop_intent，下次 explore 又 random sampling
- **修法**：explore.md 加"失败反思（必填）"段，强制 HTE 链 + 反证据 + 新假设

### 6. max_turns/rounds 太多
- **症状**：max_rounds=50 / max_turns=50 / explore_max_turns=50 浪费 token
- **修法**：砍半（25/25/20/25），优先级 explore_turns_by_priority 也降（high 18/normal 10/low 5）

## 未修（待办）

### A. claude CLI 套壳层完全替换
- **症状**：当前 worker=None 走 LLMClient.agentic（直连 deepseek），但 cfg 仍可被 `worker=claude` 切换到套壳
- **建议**：删除 `claude` worker 路径，统一用 LLMClient

### B. LLMClient.chat 用 requests.Session 但 timeout=120
- **症状**：deepseek-v4-flash 慢响应 5+ 分钟，可能 timeout
- **建议**：超时改 300s，max_tokens 改 8192

### C. reason 阶段每轮都调 LLM
- **症状**：cairn reason 阶段也调 LLM 复盘，多 1 次慢 API call
- **建议**：reason 阶段用 cheap 模型（haiku/flash）单独配置

### D. evidence 写后没触发 cairn 主动拉
- **症状**：cairn 只轮询 evidence mtime（每 30s sync_platform_cfc）
- **建议**：cairn 加 file watcher 监听 flags.notify，立即 drain

### E. bootstrap 时强制 tool discovery
- **症状**：solver 倾向 `curl + 自写 bash`，不主动 ls pocs 目录
- **修法**：已加 "Tool Discovery（必做，第 1 步）" 段到 bootstrap.md

### F. cron 强制收尾后未走 explore_conclude
- **症状**：round 没结果时 model 自己给"没招了"输出
- **建议**：reason prompt 加"round N 还在 min_rounds 之前，必须继续深挖"

### G. 同一个 flag 重复尝试没 dedup
- **症状**：cairn 提交重复 flag 报"重复提交"
- **建议**：solver 本地维护 submitted flags set（已有 _load_submitted，但只读 submission_results.jsonl）

## 不该改的（避免回归）

- `build_worker` 保留 SessionWorker 工厂（其他模式可能复用）
- loop.py 主循环保留 cairn-style graph 搜索（不是改成纯 agent loop）
- evidence dir 路径保留 `<ws>/evidence/<session>/`（cairn 兼容）
- PromptMixin 必须放在 MRO 第一位（之前修过 bug）

## 验证计划

- 起 cairn 跑 a-03 / a-05 / a-07 / e3-04（hint 备好的 4 道）
- 每题期望：5-10 分钟拿到 flag
- 监控：solver.log 应实时刷新（不再 buffering）
- 通过：a-05 LFI 读源码 → 找审批端点；a-07 XXE UTF-16 → 拿 Admin Key
