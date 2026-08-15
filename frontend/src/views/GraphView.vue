<template>
  <div>
    <div class="topbar">
      <h1>推理图</h1>
      <div class="flex muted" style="font-size:12px;">
        <span class="badge status-solved">已达成</span>
        <span class="badge status-running">进行中</span>
        <span class="badge status-failed">已丢弃</span>
      </div>
    </div>
    <div class="panel">
      <h3>facts → intents → goal 搜索图<span class="hint">MoMo 的黑板推理（cairn 式图搜索）</span></h3>
      <div class="graph-wrap">
        <VueFlow :nodes="nodes" :edges="edges" :min-zoom="0.2" :max-zoom="2" fit-view-on-init>
          <template #node-custom="slotProps">
            <div :class="['node-fact', nodeClass(slotProps.data)]">
              <div class="nid">{{ slotProps.data.label }}</div>
              <div class="mono ntitle">{{ slotProps.data.title }}</div>
              <div class="ntext">{{ slotProps.data.text }}</div>
            </div>
          </template>
          <Background :gap="26" :size="1.2" color="#1a1e3a" />
          <Controls position="bottom-right" />
        </VueFlow>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import { graph } from '../mock/data'

const LAYER = { origin: 0, i1: 1, f1: 2, i2: 1, f2: 2, i3: 1, f3: 2, i4: 1, f4: 2, goal: 4 }
const ORDER = { origin: 0, i1: 0, i2: 1, i3: 2, i4: 3, f1: 0, f2: 1, f3: 2, f4: 3, goal: 0 }

const nodes = computed(() => graph.nodes.map((n) => ({
  id: n.id,
  type: 'custom',
  position: { x: LAYER[n.id] * 260 + 20, y: ORDER[n.id] * 120 + 30 },
  data: n,
})))

const edges = computed(() => graph.edges.map((e) => ({
  id: e.id,
  source: e.from,
  target: e.to,
  type: 'smoothstep',
  className: e.type === 'done' ? 'edge-done' : e.type === 'drop' ? 'edge-drop' : '',
})))

const nodeClass = (n) => ({
  'node-goal': n.type === 'goal',
  'node-origin': n.type === 'origin',
  'node-dropped': n.dropped,
})
</script>
