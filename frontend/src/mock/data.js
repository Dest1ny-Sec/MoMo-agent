// MoMo Agent — Demo Mock Data（纯前端演示用，非真实跑分结果）

export const overview = {
  total: 63,
  solved: 31,
  score: 12850,
  running: 3,
  tokens: '4.2M',
  avgTime: '2m 41s',
  flags: 41,
}

export const dimensions = [
  { key: 'web', name: 'Web 漏洞', solved: 13, total: 18, color: '#8b5cf6' },
  { key: 'binary', name: '二进制/逆向', solved: 6, total: 13, color: '#06b6d4' },
  { key: 'exploit', name: '漏洞利用', solved: 4, total: 9, color: '#ec4899' },
  { key: 'pivot', name: '多阶段/内网', solved: 2, total: 3, color: '#10b981' },
  { key: 'cloud', name: '云攻击', solved: 3, total: 6, color: '#f59e0b' },
  { key: 'evasion', name: '对抗规避', solved: 3, total: 14, color: '#84cc16' },
]

export const trend = {
  labels: ['T-30m', 'T-25m', 'T-20m', 'T-15m', 'T-10m', 'T-5m', 'T-0'],
  scores: [4200, 5900, 7300, 9200, 10800, 12100, 12850],
  flags: [14, 19, 24, 28, 33, 37, 41],
}

export const difficulty = [
  { key: 'easy', name: '简单', solved: 12, total: 22, color: '#10b981' },
  { key: 'medium', name: '中等', solved: 11, total: 21, color: '#f59e0b' },
  { key: 'hard', name: '困难', solved: 8, total: 20, color: '#ef4444' },
]

// ---------- 图：facts / intents（MoMo 的搜索图） ----------
export const graph = {
  nodes: [
    { id: 'origin', type: 'origin', label: 'origin', title: '题目信息', text: 'TARGET: 企业内部门户\n穿透边界 WAF 获取受保护 flag' },
    { id: 'goal', type: 'goal', label: 'goal', title: '目标', text: '拿到全部 1 个 flag 并提交成功' },
    { id: 'f1', type: 'fact', label: 'f001', title: '发现', text: 'PHP 登录门户，ModSecurity WAF 防护' },
    { id: 'f2', type: 'fact', label: 'f002', title: '发现', text: '常规 SQLi 被 403 拦截，存在 WAF' },
    { id: 'f3', type: 'fact', label: 'f003', title: '发现', text: 'WAF 绕过 payload admin\';-- 注入成功' },
    { id: 'f4', type: 'fact', label: 'f004', title: '发现', text: '以 admin 登录 → dashboard 管理员区' },
    { id: 'i1', type: 'intent', label: 'i001', text: 'Web 指纹识别' },
    { id: 'i2', type: 'intent', label: 'i002', text: 'WAF 绕过尝试' },
    { id: 'i3', type: 'intent', label: 'i003', text: 'SQLi 登录绕过' },
    { id: 'i4', type: 'intent', label: 'i004', text: '读后台 flag', dropped: true },
  ],
  edges: [
    { id: 'e1', from: 'origin', to: 'i1', type: 'intent' },
    { id: 'e2', from: 'i1', to: 'f1', type: 'done' },
    { id: 'e3', from: 'f1', to: 'i2', type: 'intent' },
    { id: 'e4', from: 'i2', to: 'f2', type: 'done' },
    { id: 'e5', from: 'f2', to: 'i3', type: 'intent' },
    { id: 'e6', from: 'i3', to: 'f3', type: 'done' },
    { id: 'e7', from: 'f3', to: 'i4', type: 'intent' },
    { id: 'e8', from: 'i4', to: 'f4', type: 'done' },
    { id: 'e9', from: 'f4', to: 'goal', type: 'done' },
  ],
}

// ---------- 活动流（agent 实时动作） ----------
export const runs = [
  { ts: '18:42:11', kind: 'bootstrap', tag: 'BOOTSTRAP', text: '对 10.0.166.240 做被动侦察，识别技术栈' },
  { ts: '18:42:14', kind: 'tool', tag: 'TOOL', cmd: 'curl -sI https://10.0.166.240/ | head -20' },
  { ts: '18:42:22', kind: 'fact', tag: 'FACT', text: '识别：Vue3 + SSR，WAF 由 ModSecurity 防护' },
  { ts: '18:42:37', kind: 'tool', tag: 'TOOL', cmd: "curl -s -X POST .../login -d 'username=admin\\';--&password=x'" },
  { ts: '18:42:45', kind: 'fact', tag: 'FACT', text: 'WAF 绕过成功：注释语法注入，302 → dashboard' },
  { ts: '18:42:58', kind: 'tool', tag: 'TOOL', cmd: 'curl -s -b cj.txt .../dashboard.php | grep -E "flag|Admin"' },
  { ts: '18:43:02', kind: 'flag', tag: 'FLAG', text: 'flag{e4532c0a-9514-47fb-aeba-0c69626b5c54}' },
  { ts: '18:43:05', kind: 'submit', tag: 'SUBMIT', text: '提交成功 +250，进度 1/1，关闭容器' },
  { ts: '18:43:08', kind: 'bootstrap', tag: 'BOOTSTRAP', text: '下一题：Python 沙箱逃逸，探测 builtins' },
]

// ---------- 题目列表 ----------
export const challenges = [
  { code: 'e1-01', diff: 'medium', score: 250, status: 'solved', flags: '1/1', time: '47s' },
  { code: 'e1-02', diff: 'medium', score: 250, status: 'solved', flags: '1/1', time: '1m 12s' },
  { code: 'e1-03', diff: 'hard', score: 250, status: 'solved', flags: '1/1', time: '2m 05s' },
  { code: 'e1-04', diff: 'hard', score: 250, status: 'solved', flags: '1/1', time: '1m 48s' },
  { code: 'e2-01', diff: 'medium', score: 250, status: 'solved', flags: '1/1', time: '2m 31s' },
  { code: 'e2-02', diff: 'hard', score: 250, status: 'solved', flags: '1/1', time: '3m 20s' },
  { code: 'e2-04', diff: 'hard', score: 250, status: 'solved', flags: '1/1', time: '4m 12s' },
  { code: 'e3-02', diff: 'hard', score: 250, status: 'solved', flags: '1/1', time: '3m 44s' },
  { code: 'a-01', diff: 'hard', score: 500, status: 'solved', flags: '1/1', time: '5m 02s' },
  { code: 'a-02', diff: 'hard', score: 500, status: 'solved', flags: '1/1', time: '5m 37s' },
  { code: 'a-03', diff: 'hard', score: 500, status: 'running', flags: '0/1', time: '12m' },
  { code: 'a-04', diff: 'hard', score: 500, status: 'retry', flags: '0/1', time: '20m' },
  { code: 'a-05', diff: 'easy', score: 500, status: 'running', flags: '0/1', time: '9m' },
  { code: 'b-02', diff: 'hard', score: 500, status: 'retry', flags: '0/6', time: '20m' },
  { code: 'c-07', diff: 'hard', score: 500, status: 'failed', flags: '0/1', time: '20m' },
  { code: 'f2-05', diff: 'hard', score: 500, status: 'retry', flags: '0/1', time: '20m' },
]

export const statusLabels = { solved: '已解出', running: '求解中', retry: '待重试', pending: '排队中', failed: '未解出' }
