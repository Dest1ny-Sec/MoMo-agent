<template>
  <div>
    <div class="topbar">
      <h1>运行流</h1>
      <div class="live"><span class="dot"></span> 实时事件流</div>
    </div>
    <div class="panel">
      <h3>Agent 实时动作<span class="hint">bootstrap → reason → explore → submit</span></h3>
      <div class="feed">
        <div class="feed-item" v-for="r in runs" :key="r.ts + r.tag">
          <span class="time">{{ r.ts }}</span>
          <span class="dot" :style="{background: dotColor(r.kind)}"></span>
          <div class="body">
            <span class="tag">{{ r.tag }}</span>
            <template v-if="r.cmd"> → <span class="cmd">{{ r.cmd }}</span></template>
            <template v-else-if="r.flag"> → <span class="flag">{{ r.flag }}</span></template>
            <template v-else> → {{ r.text }}</template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { runs } from '../mock/data'
const dotColor = (k) => ({ bootstrap:'#8b5cf6', tool:'#06b6d4', fact:'#10b981', flag:'#84cc16', submit:'#10b981' }[k] || '#8a92b8')
</script>
