<template>
  <div class="donut">
    <svg viewBox="0 0 200 200" class="donut-svg">
      <g transform="rotate(-90 100 100)">
        <circle v-for="(s, i) in segments" :key="i" cx="100" cy="100" r="80"
          :fill="'none'" :stroke="s.color" :stroke-width="22"
          :stroke-dasharray="`${s.len} ${CIRC}`" :stroke-dashoffset="s.offset" />
      </g>
      <text x="100" y="94" text-anchor="middle" class="donut-val">{{ total }}</text>
      <text x="100" y="114" text-anchor="middle" class="donut-total">共 {{ total }} 题</text>
    </svg>
    <div class="legend">
      <div v-for="s in items" :key="s.name" class="legend-item">
        <span class="swatch" :style="{ background: s.color }"></span>
        <span class="legend-name">{{ s.name }}</span>
        <span class="legend-val">{{ s.solved }}/{{ s.total }}</span>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ items: { type: Array, required: true } })
const CIRC = 2 * Math.PI * 80
const total = computed(() => props.items.reduce((s, i) => s + i.total, 0))
const segments = computed(() => {
  const tot = total.value || 1
  let off = 0
  return props.items.map((it) => {
    const len = (it.total / tot) * CIRC
    const s = { color: it.color, len, offset: -off }
    off += len
    return s
  })
})
</script>
<style scoped>
.donut { display: flex; align-items: center; gap: 20px; }
.donut-svg { width: 180px; height: 180px; flex-shrink: 0; }
.donut-val { font-size: 26px; font-weight: 700; fill: var(--fg); }
.donut-total { font-size: 11px; fill: var(--fg-muted); }
.legend { display: flex; flex-direction: column; gap: 8px; flex: 1; }
.legend-item { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.swatch { width: 10px; height: 10px; border-radius: 3px; }
.legend-name { color: var(--fg-muted); flex: 1; }
.legend-val { font-family: ui-monospace, monospace; font-weight: 600; }
</style>
