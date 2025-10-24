<template>
  <div v-if="open" class="cmd-overlay" @click.self="close" role="dialog" aria-modal="true" aria-label="Command Palette">
    <div class="cmd-modal" ref="modalRef">
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        class="cmd-input"
        placeholder="Type a command or route… (e.g. 'maps', 'settings')"
        @keydown.esc.prevent="close"
        @keydown.down.prevent="move(1)"
        @keydown.up.prevent="move(-1)"
        @keydown.enter.prevent="selectActive()"
      />
      <ul class="cmd-list" role="listbox">
        <li v-for="(item, idx) in filtered" :key="item.path" :class="{active: idx === activeIndex}" role="option" @click="go(item.path)"
            @mouseenter="activeIndex = idx"
        >
          <span class="cmd-name">{{ item.name }}</span>
          <span class="cmd-path">{{ item.path }}</span>
        </li>
      </ul>
      <div class="cmd-hints">Press Esc to close • Enter to go</div>
    </div>
  </div>
  <span class="visually-hidden" aria-live="polite">Command palette {{ open ? 'opened' : 'closed' }}</span>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const open = ref(false)
const query = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const modalRef = ref<HTMLDivElement | null>(null)

const routes = computed(() => [
  { name: 'Dashboard', path: '/' },
  { name: 'Control', path: '/control' },
  { name: 'Maps', path: '/maps' },
  { name: 'Planning', path: '/planning' },
  { name: 'Mission Planner', path: '/mission-planner' },
  { name: 'Settings', path: '/settings' },
  { name: 'AI', path: '/ai' },
  { name: 'Telemetry', path: '/telemetry' },
  { name: 'Docs', path: '/docs' },
])

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return routes.value
  return routes.value.filter(r => r.name.toLowerCase().includes(q) || r.path.toLowerCase().includes(q))
})

function openPalette() {
  open.value = true
  query.value = ''
  activeIndex.value = 0
  nextTick(() => inputRef.value?.focus())
}
function close() { open.value = false }
function go(path: string) { close(); router.push(path) }
function move(dir: number) {
  if (!filtered.value.length) return
  const next = activeIndex.value + dir
  const len = filtered.value.length
  activeIndex.value = (next + len) % len
}
function selectActive() {
  const item = filtered.value[activeIndex.value]
  if (item) go(item.path)
}

function onKeydown(e: KeyboardEvent) {
  // '?' opens palette
  if (e.key === '?' || (e.shiftKey && e.key === '/')) {
    e.preventDefault(); openPalette(); return
  }
  // g d / g m quick nav when not typing in inputs
  const target = e.target as HTMLElement
  const inInput = ['INPUT','TEXTAREA'].includes(target?.tagName || '') || (target as any)?.isContentEditable
  if (inInput) return
  if (e.key.toLowerCase() === 'g') {
    // wait next key
    const onNext = (ev: KeyboardEvent) => {
      window.removeEventListener('keydown', onNext, { capture: true } as any)
      const k = ev.key.toLowerCase()
      if (k === 'd') router.push('/')
      if (k === 'm') router.push('/maps')
      if (k === 's') router.push('/settings')
      if (k === 'p') router.push('/mission-planner')
    }
    window.addEventListener('keydown', onNext, { capture: true } as any)
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.visually-hidden { position: absolute; left: -9999px; }
.cmd-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 2500;
  display: flex; align-items: flex-start; justify-content: center; padding-top: 10vh;
}
.cmd-modal {
  width: min(720px, 92vw); background: #121212; color: #e0e0e0; border-radius: 12px;
  border: 1px solid rgba(0,255,255,0.25); box-shadow: 0 30px 80px rgba(0,0,0,0.5);
}
.cmd-input { width: 100%; padding: 14px 16px; border: none; border-bottom: 1px solid rgba(0,255,255,0.2); background: transparent; color: inherit; font-size: 1rem; outline: none; }
.cmd-list { list-style: none; margin: 0; padding: 8px; max-height: 50vh; overflow: auto; }
.cmd-list li { padding: 10px 12px; border-radius: 8px; display: flex; justify-content: space-between; }
.cmd-list li.active, .cmd-list li:hover { background: rgba(0,255,255,0.08); cursor: pointer; }
.cmd-name { font-weight: 700; }
.cmd-path { opacity: 0.6; }
.cmd-hints { font-size: 0.85rem; opacity: 0.7; padding: 10px 12px; border-top: 1px solid rgba(255,255,255,0.1); }
@media (prefers-reduced-motion: reduce) { .cmd-overlay, .cmd-modal { transition: none; } }
</style>
