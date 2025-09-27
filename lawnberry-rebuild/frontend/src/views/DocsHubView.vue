<template>
  <div class="docs-view">
    <div class="page-header">
      <h1>Docs Hub</h1>
      <p class="text-muted">Project documentation</p>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-header"><strong>Documents</strong></div>
        <div class="card-body list">
          <div v-if="loadingList" class="text-muted">Loading…</div>
          <div v-else-if="listError" class="text-danger">{{ listError }}</div>
          <ul v-else>
            <li v-for="doc in docs" :key="doc.path">
              <button class="link" @click="selectDoc(doc.path)">{{ doc.name }}</button>
              <span class="muted"> ({{ doc.path }})</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><strong>Content</strong></div>
        <div class="card-body">
          <div v-if="loadingDoc" class="text-muted">Loading…</div>
          <div v-else-if="docError" class="text-danger">{{ docError }}</div>
          <div v-else class="content" v-html="contentHtml"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '@/composables/useApi'
import { renderMarkdownSafe } from '@/utils/markdown'

type DocItem = { name: string; path: string; size: number }

const docs = ref<DocItem[]>([])
const content = ref<string>('')
const loadingList = ref(true)
const loadingDoc = ref(false)
const listError = ref<string | null>(null)
const docError = ref<string | null>(null)

async function loadList() {
  loadingList.value = true
  listError.value = null
  try {
    const resp = await api.get('/docs/list')
    docs.value = resp.data
  } catch (e: any) {
    listError.value = e?.message ?? 'Failed to load list'
  } finally {
    loadingList.value = false
  }
}

async function selectDoc(path: string) {
  loadingDoc.value = true
  docError.value = null
  content.value = ''
  try {
    const resp = await api.get(`/docs/${path}`, { responseType: 'text' as any })
    content.value = resp.data
  } catch (e: any) {
    docError.value = e?.message ?? 'Failed to load document'
  } finally {
    loadingDoc.value = false
  }
}

onMounted(loadList)

const contentHtml = computed(() => renderMarkdownSafe(content.value))
</script>

<style scoped>
.grid { display: grid; grid-template-columns: 1fr; gap: 1rem; }
@media (min-width: 900px) { .grid { grid-template-columns: 1fr 2fr; } }
.card { border: 1px solid #2c3e50; border-radius: 8px; background: #0b111b; }
.card-header { padding: 0.75rem 1rem; border-bottom: 1px solid #2c3e50; }
.card-body { padding: 1rem; }
.list ul { list-style: none; padding-left: 0; }
.list li { margin-bottom: 0.25rem; }
.link { background: none; border: none; color: #58a6ff; cursor: pointer; padding: 0; }
.muted { color: #9aa4b2; font-size: 0.85rem; }
.content { line-height: 1.4; }
.content h1, .content h2, .content h3 { margin: 0.6rem 0 0.4rem; }
.content p { margin: 0.4rem 0; }
.content code, .content pre { background: #0f1722; border: 1px solid #1e293b; border-radius: 4px; padding: 0.2rem 0.35rem; }
.content pre { padding: 0.6rem; overflow: auto; }
.content a { color: #58a6ff; }
</style>
