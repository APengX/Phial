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
        <button class="ghost" :title="t('nav.graphHint')" @click="router.push({ name: 'graph' })">🕸 {{ t('nav.graph') }}</button>
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
      <button
        class="ghost upload-btn"
        :disabled="creating"
        :title="t('home.uploadHint')"
        @click="triggerUpload"
      >📤 {{ t('home.upload') }}</button>
      <input
        ref="uploadInput"
        type="file"
        accept=".pdf,.md,.markdown,.mdx,.txt,.log,.csv,.tsv,.html,.htm,image/*"
        class="hidden-input"
        @change="onFilePicked"
      />
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
        <li v-for="d in docs" :key="d.path" class="doc-card" :class="{ expanded: ctxOpen === d.path }">
          <div class="doc-row" @click="open(d.path)">
            <div class="d-avatar" aria-hidden="true">{{ initials(d.title || d.name) }}</div>
            <div class="d-titles">
              <p class="d-title">{{ d.title || d.name }}</p>
              <p class="d-sub muted">{{ d.path }} · {{ fmtTime(d.mtime) }}</p>
            </div>
            <span class="d-acts">
              <button class="d-act" :title="t('editor.rename')" @click.stop="renameDoc(d)">✎</button>
              <button class="d-act danger" :title="t('editor.delete')" @click.stop="removeDoc(d)">🗑</button>
            </span>
            <button
              class="d-act ctx-btn"
              :class="{ active: ctxOpen === d.path, has: (ctxFolders[d.path] || []).length > 0 }"
              :title="t('home.contextFolders')"
              @click.stop="toggleCtx(d.path)"
            >📁<span v-if="(ctxFolders[d.path] || []).length" class="ctx-n">{{ ctxFolders[d.path].length }}</span></button>
            <button class="ghost d-open" @click.stop="open(d.path)">{{ t('home.open') }}</button>
          </div>
          <div v-if="ctxOpen === d.path" class="ctx-panel" @click.stop>
            <div class="ctx-head muted">{{ t('home.contextHint') }}</div>
            <ul v-if="(ctxFolders[d.path] || []).length" class="ctx-list">
              <li v-for="f in ctxFolders[d.path]" :key="f.path" :class="{ missing: f.missing }">
                <span class="ctx-name">📁 {{ f.name }}</span>
                <span class="ctx-meta muted">
                  <template v-if="f.missing">{{ t('home.contextMissing') }}</template>
                  <template v-else-if="(f.pickedCount || 0) > 0">
                    {{ t('home.contextStats', { picked: f.pickedCount, total: f.fileCount, size: fmtBytes(f.totalBytes) }) }}
                  </template>
                  <template v-else>
                    {{ t('home.contextStatsEmpty', { total: f.fileCount }) }}
                  </template>
                </span>
                <code class="ctx-path muted" :title="f.path">{{ f.path }}</code>
                <button class="ctx-rm" :title="t('home.contextRemove')" @click="removeCtx(d.path, f.path)">×</button>
              </li>
            </ul>
            <div v-else class="ctx-empty muted">{{ t('home.contextEmpty') }}</div>
            <button class="ghost ctx-add" :disabled="ctxBusy" @click="addCtx(d.path)">＋ {{ t('home.contextAdd') }}</button>
          </div>
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
import { listDocuments, createDocument, getDocument, deleteDocument, renameDocument, uploadDocument } from '@/api/documents'
import {
  listAllContextFolders,
  listContextFolders,
  addContextFolder,
  removeContextFolder
} from '@/api/context'
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

// Per-document context folders (homepage UI). `ctxFolders` keeps the full
// summary array for every doc that has bindings; the badge on each doc row
// reads the length. `ctxOpen` is the path of the doc whose expanded panel
// is currently visible (single-open accordion behaviour).
const ctxFolders = ref({})
const ctxOpen = ref('')
const ctxBusy = ref(false)

watch(locale, (v) => localStorage.setItem('phial.locale', v))

async function load() {
  loading.value = true
  try {
    const ws = await getWorkspace()
    workspace.value = ws
    if (ws.agent) agent.value = ws.agent
    docs.value = await listDocuments()
    await loadContextMap()
  } catch (e) {
    pushToast(e.message, 'error')
  } finally {
    loading.value = false
  }
}

async function loadContextMap() {
  // Best-effort — failing here shouldn't break the home page; users just
  // won't see badges until they open a doc's context panel manually.
  try {
    const { byDoc } = await listAllContextFolders()
    ctxFolders.value = byDoc || {}
  } catch (e) {
    // Keep going silently; no toast — too noisy on every page load.
    ctxFolders.value = {}
  }
}

async function toggleCtx(docPath) {
  if (ctxOpen.value === docPath) {
    ctxOpen.value = ''
    return
  }
  ctxOpen.value = docPath
  // Refresh this doc's list on open so stale counts (folder moved on disk,
  // file count changed since last home-page load) get corrected.
  try {
    const { folders } = await listContextFolders(docPath)
    ctxFolders.value = { ...ctxFolders.value, [docPath]: folders }
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

async function addCtx(docPath) {
  if (ctxBusy.value) return
  // Browsers can't natively pick a folder by *absolute path*; the File System
  // Access API doesn't return one, and dialogs are sandboxed. The workspace
  // picker (`changeWorkspace`) uses the same pattern — keep consistent.
  const folder = window.prompt(t('home.contextAddPrompt'))
  if (!folder || !folder.trim()) return
  ctxBusy.value = true
  try {
    const { folders } = await addContextFolder(docPath, folder.trim())
    ctxFolders.value = { ...ctxFolders.value, [docPath]: folders }
    pushToast(t('home.contextAdded'), 'success')
  } catch (e) {
    pushToast(e.message, 'error')
  } finally {
    ctxBusy.value = false
  }
}

async function removeCtx(docPath, folder) {
  if (ctxBusy.value) return
  ctxBusy.value = true
  try {
    const { folders } = await removeContextFolder(docPath, folder)
    // Drop the key entirely when the list is empty so the badge disappears
    // instead of showing "0".
    const next = { ...ctxFolders.value }
    if (folders.length) next[docPath] = folders
    else delete next[docPath]
    ctxFolders.value = next
  } catch (e) {
    pushToast(e.message, 'error')
  } finally {
    ctxBusy.value = false
  }
}

function fmtBytes(n) {
  if (!n || n <= 0) return '0 B'
  const k = 1024
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(k)))
  return `${(n / Math.pow(k, i)).toFixed(i ? 1 : 0)} ${units[i]}`
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

const uploadInput = ref(null)
function triggerUpload() {
  if (creating.value) return
  uploadInput.value?.click()
}

async function onFilePicked(e) {
  const file = e.target.files && e.target.files[0]
  // Reset so picking the same file twice still fires `change`.
  e.target.value = ''
  if (!file || creating.value) return
  creating.value = true
  try {
    const doc = await uploadDocument(file)
    pushToast(t('home.uploadDone', { name: doc.title || doc.name }), 'success')
    open(doc.path)
  } catch (err) {
    pushToast(err.message, 'error')
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

// Two-letter monogram for a document avatar — initials of the first two
// words for latin titles, or the first two characters for CJK / single words.
function initials(name) {
  const s = (name || '').replace(/\.html?$/i, '').trim()
  if (!s) return '·'
  const words = s.split(/[\s/_-]+/).filter(Boolean)
  if (words.length >= 2 && /[A-Za-z]/.test(s)) {
    return (words[0][0] + words[1][0]).toUpperCase()
  }
  return s.slice(0, 2).toUpperCase()
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
h1 { margin: 0; font-size: 26px; }
.hero p { margin: 2px 0 0; font-size: 13px; }
.lang { padding: 5px 8px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-panel); }

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
.agent-status.ok { color: var(--success); }
.agent-status.warn { color: var(--warning); }
.agent-status:hover { background: var(--bg-soft); }

.new-doc { margin-top: 16px; display: flex; gap: 8px; align-items: center; }
.hidden-input { display: none; }
.upload-btn { white-space: nowrap; }

/* Section labels — Acme uses mono for small labels. */
.examples h2, .docs h2 {
  font-family: var(--mono); font-size: 12px; font-weight: 500; color: var(--text-mute);
  text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 12px;
}

.examples { margin-top: 32px; }
.ex-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
.ex-card {
  border: 1.5px solid var(--border-strong); border-radius: var(--radius-lg); background: var(--bg-panel);
  padding: 16px; display: flex; flex-direction: column; gap: 7px;
  transition: box-shadow 0.15s ease;
}
.ex-card:hover { outline: 2px solid var(--accent); outline-offset: 2px; }
.ex-title { font-family: var(--serif); font-size: 16px; font-weight: 500; }
.ex-desc { font-size: 12.5px; line-height: 1.55; flex: 1; }
.ex-btn { align-self: flex-start; margin-top: 4px; }

.docs { margin-top: 32px; }
.empty { padding: 24px 0; }
.doc-list { list-style: none; margin: 0; padding: 0; }
/* Acme outlined card, horizontal layout — "best for: compact row lists". */
.doc-card {
  border: 1.5px solid var(--border-strong); border-radius: var(--radius-lg); margin-bottom: 10px;
  background: var(--bg-panel); overflow: hidden;
  transition: outline-color 0.12s ease;
}
.doc-card:hover { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-card.expanded { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-row {
  display: flex; align-items: center; gap: 14px; padding: 14px 16px; cursor: pointer;
}
.d-avatar {
  width: 36px; height: 36px; border-radius: 50%; background: var(--oat);
  flex: none; display: flex; align-items: center; justify-content: center;
  font-size: 12.5px; font-weight: 600; color: var(--text); letter-spacing: 0.02em;
}
.d-titles { flex: 1; min-width: 0; }
.d-title {
  font-family: var(--serif); font-size: 16px; font-weight: 500; line-height: 1.3;
  margin: 0 0 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.d-sub {
  font-family: var(--mono); font-size: 11.5px; margin: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.d-acts { display: flex; gap: 2px; flex: none; opacity: 0; }
.doc-card:hover .d-acts, .doc-card.expanded .d-acts { opacity: 1; }
.d-act {
  border: 0; background: transparent; padding: 4px 7px; font-size: 12px; line-height: 1;
  border-radius: 6px; color: var(--text-dim);
}
.d-act:hover { background: var(--bg-soft); color: var(--text); }
.d-act.danger:hover { background: #f7eae8; color: var(--danger); }
.d-open {
  flex: none; height: 30px; padding: 0 14px; font-size: 13px;
  border: 1.5px solid var(--border-strong); border-radius: var(--radius);
}

/* Context-folders affordance: badge on the row, panel below when open. */
.ctx-btn { display: inline-flex; align-items: center; gap: 3px; }
.ctx-btn.has { color: var(--accent); opacity: 1; }
.ctx-btn.active { background: var(--accent-soft); color: var(--accent); }
.ctx-n {
  font-size: 10.5px; min-width: 14px; padding: 0 4px; border-radius: 999px;
  background: var(--accent); color: white; line-height: 1.4;
}
.ctx-btn.active .ctx-n, .ctx-btn:not(.has) .ctx-n { background: var(--text-dim); }

.ctx-panel {
  border-top: 1px dashed var(--border-strong); padding: 10px 14px 12px;
  background: rgba(217, 119, 87, 0.05);
}
.ctx-head { font-size: 11.5px; margin-bottom: 8px; line-height: 1.5; }
.ctx-list { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.ctx-list li {
  display: flex; align-items: center; gap: 10px; padding: 6px 10px;
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px;
  font-size: 12.5px;
}
.ctx-list li.missing { border-color: var(--danger); background: #f7eae8; }
.ctx-name { font-weight: 500; flex: none; }
.ctx-meta { font-size: 11.5px; flex: none; }
.ctx-path {
  font-family: var(--mono); font-size: 11px; flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  background: var(--bg-soft); padding: 1px 6px; border-radius: 4px;
}
.ctx-rm {
  border: 0; background: transparent; color: var(--text-dim);
  font-size: 16px; line-height: 1; padding: 0 6px; border-radius: 4px;
  cursor: pointer; flex: none;
}
.ctx-rm:hover { background: #f7eae8; color: var(--danger); }
.ctx-empty { font-size: 12px; padding: 4px 0 8px; }
.ctx-add { font-size: 12px; padding: 4px 10px; }
</style>
