<template>
  <div
    ref="container"
    class="virtual-joystick"
    :class="{
      'virtual-joystick--active': state.active,
      'virtual-joystick--disabled': disabled,
    }"
    :style="surfaceStyle"
    role="slider"
    aria-valuemin="-1"
    aria-valuemax="1"
    :aria-valuenow="state.active ? state.y.toFixed(2) : '0'"
    aria-label="Manual control joystick"
    @contextmenu.prevent
  >
    <div class="virtual-joystick__surface">
      <div class="virtual-joystick__ring virtual-joystick__ring--outer"></div>
      <div class="virtual-joystick__ring virtual-joystick__ring--inner"></div>
      <div class="virtual-joystick__knob" :style="knobStyle"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

interface JoystickVector {
  x: number
  y: number
  magnitude: number
  active: boolean
}

const props = defineProps({
  disabled: { type: Boolean, default: false },
  radius: { type: Number, default: 90 },
  springBack: { type: Boolean, default: true },
  deadZone: { type: Number, default: 0.08 },
})

const emit = defineEmits<{
  (e: 'start'): void
  (e: 'end'): void
  (e: 'change', vector: JoystickVector): void
}>()

const container = ref<HTMLElement | null>(null)
const state = reactive({
  x: 0,
  y: 0,
  active: false,
})

const lastVector = reactive({ x: 0, y: 0 })

const pointerSupported = typeof window !== 'undefined' && 'PointerEvent' in window
const startEvents = pointerSupported ? ['pointerdown'] : ['mousedown', 'touchstart']
const moveEvents = pointerSupported ? ['pointermove'] : ['mousemove', 'touchmove']
const endEvents = pointerSupported
  ? ['pointerup', 'pointercancel', 'pointerleave']
  : ['mouseup', 'mouseleave', 'touchend', 'touchcancel']

let activePointerId: number | null = null
const cleanupFns: Array<() => void> = []

const surfaceStyle = computed(() => {
  const size = Math.max(60, props.radius * 2)
  return {
    width: `${size}px`,
    height: `${size}px`,
  }
})

const knobStyle = computed(() => {
  const travel = props.radius * 0.75
  const translateX = state.x * travel
  const translateY = -state.y * travel
  return {
    transform: `translate(${translateX}px, ${translateY}px)`,
  }
})

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function addListener(target: EventTarget, type: string, handler: EventListenerOrEventListenerObject, options?: AddEventListenerOptions) {
  target.addEventListener(type, handler, options)
  cleanupFns.push(() => target.removeEventListener(type, handler, options))
}

function reset() {
  state.x = 0
  state.y = 0
  state.active = false
  lastVector.x = 0
  lastVector.y = 0
  emit('change', { x: 0, y: 0, magnitude: 0, active: false })
  emit('end')
}

function handleStart(rawEvent: Event) {
  if (props.disabled) {
    return
  }
  const coords = extractPoint(rawEvent)
  if (!coords) {
    return
  }
  rawEvent.preventDefault()
  rawEvent.stopPropagation()

  const pointerId = (rawEvent as PointerEvent).pointerId ?? 0
  activePointerId = pointerId
  state.active = true
  updateVector(coords.clientX, coords.clientY)
  emit('start')
}

function handleMove(rawEvent: Event) {
  if (!state.active) {
    return
  }
  if (pointerSupported && rawEvent instanceof PointerEvent) {
    if (activePointerId !== null && rawEvent.pointerId !== activePointerId) {
      return
    }
  }
  const coords = extractPoint(rawEvent)
  if (!coords) {
    return
  }
  rawEvent.preventDefault()
  updateVector(coords.clientX, coords.clientY)
}

function handleEnd(rawEvent: Event) {
  if (!state.active) {
    return
  }
  if (pointerSupported && rawEvent instanceof PointerEvent) {
    if (activePointerId !== null && rawEvent.pointerId !== activePointerId) {
      return
    }
  }
  rawEvent.preventDefault()
  activePointerId = null
  if (props.springBack) {
    reset()
  } else {
    state.active = false
    emit('end')
  }
}

function extractPoint(evt: any): { clientX: number; clientY: number } | null {
  if (typeof evt?.clientX === 'number' && typeof evt?.clientY === 'number') {
    return { clientX: evt.clientX, clientY: evt.clientY }
  }
  const touch = evt?.touches?.[0] || evt?.changedTouches?.[0]
  if (touch && typeof touch.clientX === 'number' && typeof touch.clientY === 'number') {
    return { clientX: touch.clientX, clientY: touch.clientY }
  }
  return null
}

function updateVector(clientX: number, clientY: number) {
  const el = container.value
  if (!el) {
    return
  }
  const rect = el.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  const deltaX = clientX - centerX
  const deltaY = centerY - clientY // invert so up is positive
  const normX = clamp(deltaX / props.radius, -1, 1)
  const normY = clamp(deltaY / props.radius, -1, 1)
  const magnitude = Math.sqrt(normX * normX + normY * normY)

  if (magnitude < props.deadZone) {
    state.x = 0
    state.y = 0
    emit('change', { x: 0, y: 0, magnitude: 0, active: true })
    return
  }

  const cappedMagnitude = Math.min(1, magnitude)
  const scale = cappedMagnitude === 0 ? 0 : cappedMagnitude / magnitude
  const x = normX * scale
  const y = normY * scale

  state.x = x
  state.y = y
  lastVector.x = x
  lastVector.y = y
  emit('change', { x, y, magnitude: cappedMagnitude, active: true })
}

function registerListeners() {
  const el = container.value
  if (!el) {
    return
  }
  for (const evt of startEvents) {
    addListener(el, evt, handleStart as EventListener)
  }
  if (typeof window !== 'undefined') {
    for (const evt of moveEvents) {
      addListener(window, evt, handleMove as EventListener)
    }
    for (const evt of endEvents) {
      addListener(window, evt, handleEnd as EventListener)
    }
  }
}

onMounted(() => {
  nextTick(registerListeners)
})

onBeforeUnmount(() => {
  cleanupFns.splice(0).forEach(fn => {
    try {
      fn()
    } catch {
      /* noop */
    }
  })
})

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) {
      activePointerId = null
      reset()
    }
  }
)

watch(
  () => props.springBack,
  (springBack, oldValue) => {
    if (springBack && springBack !== oldValue && !state.active) {
      reset()
    }
  }
)

function setVector(vector: { x: number; y: number }) {
  const magnitude = Math.sqrt(vector.x * vector.x + vector.y * vector.y)
  if (magnitude <= props.deadZone) {
    reset()
    return
  }
  state.x = clamp(vector.x, -1, 1)
  state.y = clamp(vector.y, -1, 1)
  state.active = true
  lastVector.x = state.x
  lastVector.y = state.y
  emit('change', {
    x: state.x,
    y: state.y,
    magnitude: Math.min(1, magnitude),
    active: true,
  })
}

defineExpose({
  reset,
  setVector,
})
</script>

<style scoped>
.virtual-joystick {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: radial-gradient(circle at center, rgba(0, 255, 146, 0.08), rgba(0, 0, 0, 0.2));
  border: 1px solid rgba(0, 255, 146, 0.25);
  transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
  touch-action: none;
  user-select: none;
}

.virtual-joystick--disabled {
  opacity: 0.45;
  pointer-events: none;
}

.virtual-joystick--active {
  box-shadow: 0 0 18px rgba(0, 255, 146, 0.35);
  border-color: rgba(0, 255, 146, 0.45);
}

.virtual-joystick__surface {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  overflow: hidden;
}

.virtual-joystick__ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(0, 255, 146, 0.35);
  pointer-events: none;
  inset: 10%;
}

.virtual-joystick__ring--inner {
  inset: 35%;
  border-color: rgba(0, 255, 146, 0.55);
}

.virtual-joystick__knob {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 42px;
  height: 42px;
  margin: -21px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, rgba(0, 255, 146, 0.8), rgba(0, 44, 31, 0.85));
  border: 1px solid rgba(0, 255, 146, 0.65);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
  transition: transform 0.05s ease-out;
  pointer-events: none;
}
</style>
