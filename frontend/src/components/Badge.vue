<template>
  <span class="badge" :class="cls"><slot /></span>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ type: { type: String, default: 'info' } })
const cls = computed(() => ({
  'sev-critical': props.type === 'critical',
  'sev-high': props.type === 'high',
  'sev-medium': props.type === 'medium',
  'sev-low': props.type === 'low',
  'sev-info': props.type === 'info',
  'status-solved': props.type === 'solved',
  'status-running': props.type === 'running',
  'status-pending': props.type === 'pending',
  'status-retry': props.type === 'retry',
  'status-failed': props.type === 'failed',
}))
</script>
