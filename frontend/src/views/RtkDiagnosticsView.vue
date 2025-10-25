<template>
  <div class="view">
    <div class="page-header">
      <h1>RTK Diagnostics</h1>
      <p class="text-muted">Live NTRIP throughput and GPS fix quality</p>
    </div>
    <RtkDiagnosticsPanel />
  </div>
</template>

<script setup lang="ts">
import RtkDiagnosticsPanel from '@/components/RtkDiagnosticsPanel.vue'
</script>

<style scoped>
.view { padding: 0; }
.page-header { margin-bottom: 1rem; }
.page-header h1 { margin: 0 0 .25rem; }
.text-muted { color: var(--text-muted); }
</style>
