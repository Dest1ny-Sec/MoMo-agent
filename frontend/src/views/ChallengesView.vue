<template>
  <div>
    <div class="topbar">
      <h1>题目</h1>
      <div class="flex muted" style="font-size:12px;">
        共 {{ challenges.length }} 道 · 已解 {{ solvedCount }} 道
      </div>
    </div>
    <div class="panel">
      <h3>任务队列<span class="hint">两轮制：每题 20 分钟，没解出进重试队列，全部尝试后第二轮</span></h3>
      <table class="table">
        <thead>
          <tr><th>题目</th><th>难度</th><th>分值</th><th>状态</th><th>flags</th><th>耗时</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in challenges" :key="c.code">
            <td class="mono">{{ c.code }}</td>
            <td><Badge :type="c.diff">{{ diffLabel(c.diff) }}</Badge></td>
            <td>{{ c.score }}</td>
            <td><Badge :type="c.status">{{ statusLabels[c.status] }}</Badge></td>
            <td class="mono">{{ c.flags }}</td>
            <td class="mono muted">{{ c.time }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script setup>
import Badge from '../components/Badge.vue'
import { challenges, statusLabels } from '../mock/data'
const diffLabel = (d) => ({ easy: '简单', medium: '中等', hard: '困难' }[d] || d)
const solvedCount = challenges.filter((c) => c.status === 'solved').length
</script>
