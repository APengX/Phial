<template>
  <div class="doc-summary" :class="{ collapsed }">
    <div class="ds-head" @click="collapsed = !collapsed">
      <span class="ds-caret">{{ collapsed ? '▸' : '▾' }}</span>
      <span class="ds-title">✦ {{ t('nav.summary') }}</span>
      <span class="ds-read muted">· {{ t('nav.readMin', { n: stats.readMin }) }}</span>
      <span class="ds-spacer"></span>
      <span
        v-if="stale && summary"
        class="ds-staleflag"
        :title="t('nav.summaryStale')"
      >●</span>
    </div>

    <div v-show="!collapsed" class="ds-body">
      <div class="ds-chips">
        <span class="ds-chip">{{ t('nav.statWords', { n: fmt(stats.words) }) }}</span>
        <span v-if="stats.sections" class="ds-chip">{{ t('nav.statSections', { n: stats.sections }) }}</span>
        <span v-if="stats.tables" class="ds-chip">{{ t('nav.statTables', { n: stats.tables }) }}</span>
        <span v-if="stats.widgets" class="ds-chip hot">{{ t('nav.statWidgets', { n: stats.widgets }) }}</span>
        <span v-if="stats.images" class="ds-chip">{{ t('nav.statImages', { n: stats.images }) }}</span>
      </div>

      <div class="ds-ai">
        <p v-if="loading" class="ds-text muted">{{ t('nav.summaryGenerating') }}</p>
        <p v-else-if="error" class="ds-text err">{{ error }}</p>
        <template v-else-if="summary">
          <p class="ds-text">{{ summary }}</p>
          <div class="ds-aifoot">
            <span v-if="stale" class="ds-stalenote">{{ t('nav.summaryStale') }}</span>
            <button class="ghost ds-regen" @click="generate(true)">↻ {{ t('nav.summaryRegen') }}</button>
          </div>
        </template>
        <template v-else>
          <button class="primary ds-gen" :disabled="!canGen" @click="generate(false)">
            ✦ {{ t('nav.summaryGen') }}
          </button>
          <span class="ds-hint muted">{{ t('nav.summaryHint') }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSummary } from '@/api/ai'

const props = defineProps({
  html: { type: String, default: '' },
  path: { type: String, default: '' }
})
const { t } = useI18n()

const collapsed = ref(localStorage.getItem('phial.summaryCollapsed') === '1')
watch(collapsed, (v) => localStorage.setItem('phial.summaryCollapsed', v ? '1' : '0'))

const summary = ref('')
const summaryHtml = ref('') // the html the current summary was generated from
const loading = ref(false)
const error = ref('')
let reqId = 0

const canGen = computed(() => !loading.value && !!props.html.trim())
// The summary went out of date once the document was edited past it.
const stale = computed(() => !!summary.value && props.html !== summaryHtml.value)

// --- instant, AI-free structure stats ---------------------------------------
const stats = computed(() => {
  const r = { words: 0, readMin: 1, sections: 0, tables: 0, widgets: 0, images: 0 }
  if (!props.html) return r
  try {
    const body = new DOMParser().parseFromString(props.html, 'text/html').body
    if (!body) return r
    const txt = (body.textContent || '').trim()
    const cjk = (txt.match(/[㐀-鿿]/g) || []).length
    const latin = (txt.replace(/[㐀-鿿]/g, ' ').match(/[A-Za-z0-9]+/g) || []).length
    r.words = cjk + latin
    r.readMin = Math.max(1, Math.round(r.words / 400))
    r.sections = body.querySelectorAll('h1,h2,h3').length
    r.tables = body.querySelectorAll('table').length
    r.images = body.querySelectorAll('img').length
    r.widgets = body.querySelectorAll('script').length
  } catch {
    /* ignore malformed HTML */
  }
  return r
})

function fmt(n) {
  return n >= 10000 ? (n / 10000).toFixed(1) + 'w' : String(n)
}

// --- AI summary --------------------------------------------------------------
async function peek() {
  summary.value = ''
  error.value = ''
  if (!props.html.trim()) return
  const id = ++reqId
  try {
    const r = await getSummary(props.path, props.html, { peek: true })
    if (id !== reqId) return
    if (r && r.summary) {
      summary.value = r.summary
      summaryHtml.value = props.html
    }
  } catch {
    /* peek is best-effort — stay silent, the button is still there */
  }
}

async function generate(refresh) {
  if (!canGen.value) return
  const id = ++reqId
  loading.value = true
  error.value = ''
  try {
    const r = await getSummary(props.path, props.html, { refresh })
    if (id !== reqId) return
    summary.value = (r && r.summary) || ''
    summaryHtml.value = props.html
  } catch (e) {
    if (id === reqId) error.value = e.message || 'failed'
  } finally {
    if (id === reqId) loading.value = false
  }
}

// Peek once per document — the first time its HTML is available. The editor
// loads `html` asynchronously after mount, so we can't just peek on mount.
let peekedFor = null
function maybePeek() {
  if (!props.html.trim() || peekedFor === props.path) return
  peekedFor = props.path
  peek()
}
watch(() => props.path, () => {
  peekedFor = null
  summary.value = ''
  error.value = ''
})
watch(() => props.html, maybePeek)
onMounted(maybePeek)
</script>

<style scoped>
.doc-summary {
  flex: none;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  font-size: 13px;
}
.ds-head {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 12px; cursor: pointer; user-select: none;
}
.ds-head:hover { background: var(--bg-soft); }
.ds-caret { color: var(--text-dim); font-size: 10px; width: 10px; }
.ds-title { font-weight: 600; color: var(--accent); }
.ds-read { font-size: 12px; }
.ds-spacer { flex: 1; }
.ds-staleflag { color: var(--warning); font-size: 9px; }

.ds-body { padding: 2px 12px 12px; }
.ds-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.ds-chip {
  font-size: 11.5px; padding: 2px 8px; border-radius: 999px;
  background: var(--bg-soft); color: var(--text-dim);
}
.ds-chip.hot { background: var(--accent-soft); color: var(--accent); }

.ds-ai { display: flex; flex-direction: column; gap: 7px; }
.ds-text { margin: 0; line-height: 1.6; color: var(--text); }
.ds-text.err { color: var(--danger); }
.ds-aifoot { display: flex; align-items: center; gap: 10px; }
.ds-stalenote { font-size: 11.5px; color: var(--warning); }
.ds-regen { font-size: 12px; padding: 3px 9px; color: var(--text-dim); }
.ds-gen { align-self: flex-start; }
.ds-hint { font-size: 11.5px; line-height: 1.55; }
</style>
