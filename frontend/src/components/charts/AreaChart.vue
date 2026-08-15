<template>
  <svg :viewBox="`0 0 ${W} ${H}`" class="area" preserveAspectRatio="none">
    <defs>
      <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="color" stop-opacity="0.35" />
        <stop offset="100%" :stop-color="color" stop-opacity="0.02" />
      </linearGradient>
    </defs>
    <path :d="areaPath" :fill="`url(#${gid})`" />
    <path :d="linePath" :fill="'none'" :stroke="color" stroke-width="2.5" stroke-linejoin="round" />
    <circle v-for="(p, i) in pts" :key="i" :cx="p.x" :cy="p.y" r="3" :fill="color">
      <title>{{ labels[i] }}: {{ values[i] }}</title>
    </circle>
  </svg>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ values: Array, labels: Array, color: { type: String, default: '#8b5cf6' } })
const W = 600, H = 200, PAD = 8
const gid = 'area-' + Math.random().toString(36).slice(2, 8)
const pts = computed(() => {
  const max = Math.max(...props.values) || 1
  const min = Math.min(...props.values) || 0
  const span = (max - min) || 1
  const n = props.values.length
  return props.values.map((v, i) => ({
    x: PAD + (i / (n - 1)) * (W - 2 * PAD),
    y: H - PAD - ((v - min) / span) * (H - 2 * PAD),
  }))
})
const linePath = computed(() => pts.value.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' '))
const areaPath = computed(() => `${linePath.value} L${pts.value[pts.value.length - 1].x},${H} L${pts.value[0].x},${H} Z`)
</script>
<style scoped>
.area { width: 100%; height: 200px; }
</style>
