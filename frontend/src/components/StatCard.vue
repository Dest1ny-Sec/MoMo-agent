<template>
  <div class="stat-card" :class="tone">
    <div class="label">{{ label }}</div>
    <div class="value">{{ value }}<span v-if="unit" class="unit">{{ unit }}</span></div>
    <div v-if="sub" class="sub">{{ sub }}</div>
  </div>
</template>
<script setup>
defineProps({
  label: String,
  value: [String, Number],
  unit: String,
  sub: String,
  tone: String,
})
</script>
