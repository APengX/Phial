<template>
  <div class="home">
    <header class="hero">
      <div class="brand">
        <img class="logo" src="/icon.svg" alt="Phial" width="46" height="46" />
        <div>
          <h1>{{ t('app.name') }}</h1>
          <p class="muted">{{ t('app.tagline') }}</p>
        </div>
      </div>
      <div class="row">
        <button class="ghost" :title="t('settings.open')" @click="settingsOpen = true">⚙ {{ t('settings.open') }}</button>
        <select v-model="locale" class="lang" :title="t('common.language')">
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
      </div>
    </header>

    <section class="ws-bar">
      <div class="row" style="gap:8px; min-width:0;">
        <span class="muted">{{ t('home.workspace') }}:</span>
        <code class="ws-path" :title="workspace.root">{{ workspace.root || '…' }}</code>
        <button class="ghost" @click="changeWorkspace">{{ t('home.changeWorkspace') }}</button>
      </div>
      <button class="agent-status" :class="agent.ready ? 'ok' : 'warn'" @click="settingsOpen = true">
        <span class="dot"></span>{{ agent.label || '…' }}
      </button>
    </section>

    <SettingsModal v-model="settingsOpen" @saved="onAgentSaved" />

    <section class="new-doc">
      <input
        v-model="newName"
        :placeholder="t('home.newDocName')"
        @keydown.enter="create"
        style="flex:1;"
      />
      <button class="primary" :disabled="!newName.trim() || creating" @click="create">
        {{ t('home.newDoc') }}
      </button>
    </section>

    <section class="examples">
      <h2>{{ t('home.examples') }}</h2>
      <div class="ex-grid">
        <div v-for="ex in examples" :key="ex.id" class="ex-card">
          <div class="ex-title">{{ ex.title[locale] || ex.title.en }}</div>
          <div class="ex-desc muted">{{ ex.desc[locale] || ex.desc.en }}</div>
          <button class="primary ex-btn" :disabled="creating" @click="useExample(ex)">{{ t('home.useExample') }}</button>
        </div>
      </div>
    </section>

    <section class="docs">
      <h2>{{ t('home.recent') }}</h2>
      <p v-if="!loading && docs.length === 0" class="muted empty">{{ t('home.noDocs') }}</p>
      <p v-if="loading" class="muted">{{ t('common.loading') }}</p>
      <ul class="doc-list">
        <li v-for="d in docs" :key="d.path" @click="open(d.path)">
          <span class="d-icon">📄</span>
          <span class="d-title">{{ d.title || d.name }}</span>
          <span class="d-path muted">{{ d.path }}</span>
          <span class="d-acts">
            <button class="d-act" :title="t('editor.rename')" @click.stop="renameDoc(d)">✎</button>
            <button class="d-act danger" :title="t('editor.delete')" @click.stop="removeDoc(d)">🗑</button>
          </span>
          <span class="d-time muted">{{ fmtTime(d.mtime) }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getWorkspace, setWorkspace } from '@/api/workspace'
import { listDocuments, createDocument, getDocument, deleteDocument, renameDocument } from '@/api/documents'
import { pushToast } from '@/composables/useToast'
import { EXAMPLES } from '@/examples'
import SettingsModal from '@/components/SettingsModal.vue'

const router = useRouter()
const { t, locale } = useI18n()

const workspace = ref({ root: '' })
const agent = ref({ label: '', ready: true })
const settingsOpen = ref(false)
const docs = ref([])
const loading = ref(true)
const newName = ref('')
const creating = ref(false)
const examples = EXAMPLES

watch(locale, (v) => localStorage.setItem('phial.locale', v))

async function load() {
  loading.value = true
  try {
    const ws = await getWorkspace()
    workspace.value = ws
    if (ws.agent) agent.value = ws.agent
    docs.value = await listDocuments()
  } catch (e) {
    pushToast(e.message, 'error')
  } finally {
    loading.value = false
  }
}

function onAgentSaved(active) {
  if (active) agent.value = active
}

async function changeWorkspace() {
  const p = window.prompt(t('home.changeWorkspace'), workspace.value.root)
  if (!p || p === workspace.value.root) return
  try {
    await setWorkspace(p)
    await load()
    pushToast(t('home.workspace') + ' → ' + p, 'success')
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

async function create() {
  const name = newName.value.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    const doc = await createDocument({ path: name })
    newName.value = ''
    open(doc.path)
  } catch (e) {
    pushToast(e.message, 'error')
  } finally {
    creating.value = false
  }
}

async function useExample(ex) {
  if (creating.value) return
  creating.value = true
  try {
    // already in the workspace? just open it.
    try {
      const existing = await getDocument(ex.defaultPath)
      open(existing.path)
      return
    } catch (_) {
      /* not there yet — create it below */
    }
    const resp = await fetch(ex.file)
    if (!resp.ok) throw new Error('无法加载示例文件')
    const html = await resp.text()
    const doc = await createDocument({ path: ex.defaultPath, html })
    open(doc.path)
  } catch (e) {
    pushToast(e.message, 'error')
  } finally {
    creating.value = false
  }
}

async function removeDoc(d) {
  if (!window.confirm(t('editor.confirmDelete', { name: d.title || d.name || d.path }))) return
  try {
    await deleteDocument(d.path)
    pushToast(t('editor.delete') + ' ✓', 'success')
    docs.value = await listDocuments()
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

async function renameDoc(d) {
  const dst = window.prompt(t('editor.renamePrompt'), d.path)
  if (!dst || dst === d.path) return
  try {
    await renameDocument(d.path, dst)
    pushToast(t('editor.rename') + ' ✓', 'success')
    docs.value = await listDocuments()
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

function open(path) {
  router.push({ name: 'editor', query: { path } })
}

function fmtTime(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

onMounted(load)
</script>

<style scoped>
.home { max-width: 860px; margin: 0 auto; padding: 32px 24px 64px; }
.hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.brand { display: flex; gap: 14px; align-items: center; }
.logo { width: 46px; height: 46px; border-radius: 11px; display: block; }
h1 { margin: 0; font-size: 24px; }
.hero p { margin: 2px 0 0; font-size: 13px; }
.lang { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-panel); }

.ws-bar {
  margin-top: 24px; padding: 12px 14px; background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: var(--radius); display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
}
.ws-path {
  font-family: var(--mono); font-size: 12px; background: var(--bg-soft); padding: 3px 7px; border-radius: 5px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 380px;
}
.agent-status {
  font-size: 12px; display: flex; align-items: center; gap: 7px; border-radius: 999px;
  padding: 4px 11px; border-color: var(--border); background: var(--bg-panel);
}
.agent-status .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex: none; }
.agent-status.ok { color: #047857; }
.agent-status.warn { color: #b45309; }
.agent-status:hover { background: var(--bg-soft); }

.new-doc { margin-top: 16px; display: flex; gap: 8px; }

.examples { margin-top: 32px; }
.examples h2 { font-size: 14px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10px; }
.ex-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.ex-card {
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-panel);
  padding: 14px; display: flex; flex-direction: column; gap: 7px;
}
.ex-title { font-weight: 600; }
.ex-desc { font-size: 12.5px; line-height: 1.55; flex: 1; }
.ex-btn { align-self: flex-start; margin-top: 4px; }

.docs { margin-top: 32px; }
.docs h2 { font-size: 14px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10px; }
.empty { padding: 24px 0; }
.doc-list { list-style: none; margin: 0; padding: 0; }
.doc-list li {
  display: flex; align-items: center; gap: 10px; padding: 9px 12px; border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 8px; cursor: pointer; background: var(--bg-panel);
}
.doc-list li:hover { border-color: var(--accent); background: #faf5ff; }
.d-icon { font-size: 15px; flex: none; }
.d-title { font-weight: 500; flex: none; }
.d-path { font-family: var(--mono); font-size: 11.5px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.d-acts { margin-left: auto; display: flex; gap: 2px; flex: none; opacity: 0; }
.doc-list li:hover .d-acts { opacity: 1; }
.d-act {
  border: 0; background: transparent; padding: 2px 6px; font-size: 12px; line-height: 1;
  border-radius: 5px; color: var(--text-dim);
}
.d-act:hover { background: var(--bg-soft); color: var(--text); }
.d-act.danger:hover { background: #fef2f2; color: var(--danger); }
.d-time { font-size: 11.5px; white-space: nowrap; flex: none; }
</style>
