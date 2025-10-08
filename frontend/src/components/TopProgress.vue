<template>
  <div class="top-progress" v-show="visible">
    <div class="bar" :style="{ width: width + '%' }" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const visible = ref(false)
const width = ref(0)
let timer: number | null = null

function start() {
  visible.value = true
  width.value = 10
  if (timer) window.clearInterval(timer)
  timer = window.setInterval(() => {
    width.value = Math.min(98, width.value + Math.random() * 8)
  }, 200)
}

function done() {
  if (timer) { window.clearInterval(timer); timer = null }
  width.value = 100
  setTimeout(() => { visible.value = false; width.value = 0 }, 200)
}

// Expose control for router hooks
// @ts-ignore
window.__TopProgress = { start, done }

onUnmounted(() => { if (timer) window.clearInterval(timer) })
</script>

<style scoped>
.top-progress {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  z-index: 3000;
}
.bar {
  height: 100%;
  background: linear-gradient(90deg, #00ff92, #00c8ff, #ff00ff);
  box-shadow: 0 0 12px rgba(0,255,146,0.6);
  transition: width .2s ease;
}
</style>
