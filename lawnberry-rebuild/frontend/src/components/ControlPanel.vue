<template>
  <div class="control-panel">
    <div class="panel-header">
      <h3>{{ title }}</h3>
      <div v-if="status" class="panel-status" :class="status">
        {{ statusText }}
      </div>
    </div>
    
    <div class="panel-body">
      <slot></slot>
    </div>
    
    <div v-if="$slots.actions" class="panel-actions">
      <slot name="actions"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  title: string
  status?: 'active' | 'inactive' | 'warning' | 'error'
}

const props = withDefaults(defineProps<Props>(), {
  status: undefined
})

const statusText = computed(() => {
  switch (props.status) {
    case 'active': return 'Active'
    case 'inactive': return 'Inactive'
    case 'warning': return 'Warning'
    case 'error': return 'Error'
    default: return ''
  }
})
</script>

<style scoped>
.control-panel {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  background-color: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
}

.panel-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #2c3e50;
}

.panel-status {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.panel-status.active {
  background-color: #d4edda;
  color: #155724;
}

.panel-status.inactive {
  background-color: #f8d7da;
  color: #721c24;
}

.panel-status.warning {
  background-color: #fff3cd;
  color: #856404;
}

.panel-status.error {
  background-color: #f8d7da;
  color: #721c24;
}

.panel-body {
  padding: 1.5rem;
}

.panel-actions {
  padding: 1rem 1.5rem;
  background-color: #f8f9fa;
  border-top: 1px solid #e9ecef;
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

/* Mobile-first responsive design */
@media (max-width: 480px) {
  .control-panel {
    border-radius: 12px;
    margin-bottom: 1rem;
  }
  
  .panel-header {
    padding: 1rem;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }
  
  .panel-header h3 {
    font-size: 1.125rem;
    text-align: center;
    width: 100%;
  }
  
  .panel-status {
    align-self: center;
    padding: 0.5rem 1rem;
    font-size: 0.8rem;
  }
  
  .panel-body {
    padding: 1rem;
  }
  
  .panel-actions {
    padding: 1rem;
    gap: 0.5rem;
    flex-direction: column;
  }
  
  .panel-actions .btn {
    width: 100%;
    justify-content: center;
  }
}

@media (min-width: 481px) and (max-width: 768px) {
  .panel-header {
    padding: 1.25rem;
    gap: 0.75rem;
  }
  
  .panel-body {
    padding: 1.25rem;
  }
  
  .panel-actions {
    padding: 1rem 1.25rem;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
}
</style>