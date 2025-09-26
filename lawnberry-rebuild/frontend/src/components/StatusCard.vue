<template>
  <div class="status-card" :class="status">
    <div class="status-header">
      <div class="status-icon">
        <slot name="icon">
          <div class="status-dot"></div>
        </slot>
      </div>
      <div class="status-content">
        <h4 class="status-title">{{ title }}</h4>
        <p class="status-description">{{ description }}</p>
      </div>
    </div>
    
    <div v-if="$slots.details" class="status-details">
      <slot name="details"></slot>
    </div>
    
    <div v-if="$slots.actions" class="status-actions">
      <slot name="actions"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  title: string
  description?: string
  status?: 'active' | 'warning' | 'error' | 'inactive' | 'unknown'
}

withDefaults(defineProps<Props>(), {
  description: '',
  status: 'inactive'
})
</script>

<style scoped>
.status-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 1.5rem;
  transition: all 0.2s ease;
  border-left: 4px solid #dee2e6;
}

.status-card.active {
  border-left-color: #27ae60;
  background-color: rgba(39, 174, 96, 0.02);
}

.status-card.warning {
  border-left-color: #f39c12;
  background-color: rgba(243, 156, 18, 0.02);
}

.status-card.error {
  border-left-color: #e74c3c;
  background-color: rgba(231, 76, 60, 0.02);
}

.status-card.unknown {
  border-left-color: #95a5a6;
  background-color: rgba(149, 165, 166, 0.02);
}

.status-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.status-icon {
  flex-shrink: 0;
  margin-top: 0.25rem;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: #dee2e6;
}

.active .status-dot {
  background-color: #27ae60;
}

.warning .status-dot {
  background-color: #f39c12;
}

.error .status-dot {
  background-color: #e74c3c;
}

.unknown .status-dot {
  background-color: #95a5a6;
}

.status-content {
  flex: 1;
}

.status-title {
  margin: 0 0 0.25rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: #2c3e50;
}

.status-description {
  margin: 0;
  color: #6c757d;
  font-size: 0.875rem;
  line-height: 1.4;
}

.status-details {
  padding: 1rem 0 0;
  border-top: 1px solid #e9ecef;
  margin-top: 1rem;
}

.status-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}

@media (max-width: 768px) {
  .status-card {
    padding: 1rem;
  }
  
  .status-header {
    gap: 0.75rem;
  }
  
  .status-actions {
    gap: 0.5rem;
  }
}
</style>