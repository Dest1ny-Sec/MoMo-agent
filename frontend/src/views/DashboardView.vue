<template>
  <div>
    <div class="topbar">
      <h1>总览</h1>
      <div class="live"><span class="dot"></span> 实时监控中 · 3 个任务运行中</div>
    </div>

    <div class="stat-row">
      <StatCard label="已完成题目" :value="overview.solved" :sub="`共 ${overview.total} 道`" tone="accent" />
      <StatCard label="累计得分" :value="overview.score.toLocaleString()" unit="分" tone="ok" />
      <StatCard label="已提交 flag" :value="overview.flags" sub="跨 31 道题" tone="cyan" />
      <StatCard label="平均耗时" :value="overview.avgTime" sub="每道题" tone="amber" />
      <StatCard label="Token 消耗" :value="overview.tokens" sub="整个任务窗口" />
    </div>

    <div class="chart-row">
      <div class="panel">
        <h3>维度攻克率<span class="hint">6 大评测维度</span></h3>
        <DonutChart :items="dimensions" />
      </div>
      <div class="panel">
        <h3>得分趋势<span class="hint">近 30 分钟</span></h3>
        <AreaChart :values="trend.scores" :labels="trend.labels" color="#8b5cf6" />
        <div class="flex muted" style="justify-content:space-between;margin-top:8px;font-size:11px;">
          <span v-for="(l, i) in trend.labels" :key="i">{{ l }}</span>
        </div>
      </div>
    </div>

    <div class="grid-2" style="margin-top:18px;">
      <div class="panel">
        <h3>难度分布</h3>
        <div class="diff-list">
          <div v-for="d in difficulty" :key="d.key" class="diff-item">
            <div class="flex"><span class="swatch" :style="{background:d.color}"></span>
              <span>{{ d.name }}</span><span class="muted">· {{ d.solved }}/{{ d.total }}</span></div>
            <div class="bar"><div class="bar-fill" :style="{width: pct(d)+'%', background:d.color}"></div></div>
          </div>
        </div>
      </div>
      <div class="panel">
        <h3>当前运行</h3>
        <div class="feed">
          <div class="feed-item" v-for="r in live" :key="r.ts">
            <span class="time">{{ r.ts }}</span>
            <span class="dot" :style="{background: dotColor(r.kind)}"></span>
            <div class="body">
              <span class="tag">{{ r.tag }}</span>
              <template v-if="r.cmd"> <span class="cmd">{{ r.cmd }}</span></template>
              <template v-else-if="r.flag"> <span class="flag">{{ r.flag }}</span></template>
              <template v-else> {{ r.text }}</template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import StatCard from '../components/StatCard.vue'
import DonutChart from '../components/charts/DonutChart.vue'
import AreaChart from '../components/charts/AreaChart.vue'
import { overview, dimensions, trend, difficulty, runs } from '../mock/data'

const pct = (d) => Math.round((d.solved / d.total) * 100)
const dotColor = (k) => ({ bootstrap:'#8b5cf6', tool:'#06b6d4', fact:'#10b981', flag:'#84cc16', submit:'#10b981' }[k] || '#8a92b8')
const live = ref(runs.slice(0, 8))
</script>
<style scoped>
.diff-list { display: flex; flex-direction: column; gap: 12px; }
.diff-item { display: flex; flex-direction: column; gap: 5px; font-size: 13px; }
.swatch { width: 10px; height: 10px; border-radius: 3px; }
.bar { height: 6px; background: var(--bg-elev); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; }
</style>
