<template>
  <div class="metric-widget" :class="`metric-${variant}`">
    <div class="metric-header">
      <div class="metric-icon" v-if="icon">
        <slot name="icon">{{ icon }}</slot>
      </div>
      <div class="metric-info">
        <h4 class="metric-label">{{ label }}</h4>
        <div class="metric-value">
          {{ formattedValue }}
          <span v-if="unit" class="metric-unit">{{ unit }}</span>
        </div>
      </div>
    </div>
    
    <div v-if="showProgress && typeof value === 'number'" class="metric-progress">
      <div class="progress-bar">
        <div 
          class="progress-fill" 
          :style="`width: ${progressPercentage}%`"
        ></div>
      </div>
      <div class="progress-text">
        {{ progressPercentage }}% {{ progressLabel }}
      </div>
    </div>
    
    <div v-if="trend !== undefined" class="metric-trend" :class="trendClass">
      <span class="trend-icon">{{ trendIcon }}</span>
      <span class="trend-text">{{ trendText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  label: string
  value: number | string
  unit?: string
  icon?: string
  showProgress?: boolean
  maxValue?: number
  trend?: number
  variant?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
  progressLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  unit: '',
  icon: '',
  showProgress: false,
  maxValue: 100,
  trend: undefined,
  variant: 'primary',
  progressLabel: 'complete'
})

const formattedValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString()
  }
  return props.value
})

const progressPercentage = computed(() => {
  if (typeof props.value === 'number' && props.maxValue > 0) {
    return Math.min(Math.max((props.value / props.maxValue) * 100, 0), 100)
  }
  return 0
})

const trendClass = computed(() => {
  if (props.trend === undefined) return ''
  if (props.trend > 0) return 'trend-up'
  if (props.trend < 0) return 'trend-down'
  return 'trend-neutral'
})

const trendIcon = computed(() => {
  if (props.trend === undefined) return ''
  if (props.trend > 0) return '↗'
  if (props.trend < 0) return '↘'
  return '→'
})

const trendText = computed(() => {
  if (props.trend === undefined) return ''
  const absValue = Math.abs(props.trend)
  if (props.trend > 0) return `+${absValue}%`
  if (props.trend < 0) return `-${absValue}%`
  return '0%'
})
</script>

<style scoped>
.metric-widget {
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;
  border-left: 4px solid #3498db;
}

.metric-primary {
  border-left-color: #3498db;
}

.metric-success {
  border-left-color: #27ae60;
}

.metric-warning {
  border-left-color: #f39c12;
}

.metric-danger {
  border-left-color: #e74c3c;
}

.metric-info {
  border-left-color: #17a2b8;
}

.metric-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.metric-icon {
  font-size: 1.5rem;
  color: #6c757d;
  min-width: 2rem;
  text-align: center;
}

.metric-info {
  flex: 1;
}

.metric-label {
  margin: 0 0 0.25rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: #6c757d;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.metric-value {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
  color: #2c3e50;
  line-height: 1;
}

.metric-unit {
  font-size: 1rem;
  font-weight: 400;
  color: #6c757d;
  margin-left: 0.25rem;
}

.metric-progress {
  margin-top: 1rem;
}

.progress-bar {
  height: 8px;
  background-color: #e9ecef;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background-color: #3498db;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.metric-primary .progress-fill {
  background-color: #3498db;
}

.metric-success .progress-fill {
  background-color: #27ae60;
}

.metric-warning .progress-fill {
  background-color: #f39c12;
}

.metric-danger .progress-fill {
  background-color: #e74c3c;
}

.metric-info .progress-fill {
  background-color: #17a2b8;
}

.progress-text {
  font-size: 0.75rem;
  color: #6c757d;
  text-align: center;
}

.metric-trend {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.trend-up {
  color: #27ae60;
}

.trend-down {
  color: #e74c3c;
}

.trend-neutral {
  color: #6c757d;
}

.trend-icon {
  font-size: 1rem;
}

/* Mobile-first responsive design */
@media (max-width: 480px) {
  .metric-widget {
    padding: 1rem;
    margin-bottom: 1rem;
  }
  
  .metric-header {
    gap: 0.75rem;
    align-items: center;
  }
  
  .metric-icon {
    font-size: 1.25rem;
    min-width: 1.5rem;
  }
  
  .metric-value {
    font-size: 1.75rem;
    line-height: 1.1;
  }
  
  .metric-unit {
    font-size: 0.875rem;
  }
  
  .metric-label {
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
  }
  
  .progress-text {
    font-size: 0.8rem;
  }
  
  .metric-trend {
    margin-top: 0.5rem;
    font-size: 0.8rem;
  }
}

@media (min-width: 481px) and (max-width: 768px) {
  .metric-widget {
    padding: 1.25rem;
  }
  
  .metric-value {
    font-size: 1.75rem;
  }
  
  .metric-header {
    gap: 1rem;
  }
}
</style>