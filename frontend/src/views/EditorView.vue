<template>
  <div class="editor-shell">
    <!-- top bar -->
    <header class="topbar">
      <button class="ghost" @click="goHome">‹ {{ t('editor.back') }}</button>
      <button class="ghost icon-btn" @click="showTree = !showTree" :title="'Sidebar'">☰</button>

      <div class="doc-id" :title="currentPath">
        <strong>{{ doc?.title || doc?.name || '…' }}</strong>
        <code class="muted">{{ currentPath }}</code>
        <span class="dirty" :class="{ on: dirty }">{{ dirty ? '● ' + t('editor.unsaved') : t('editor.saved') }}</span>
        <button
          v-if="interfaceState != null"
          class="ghost state-pill"
          :title="t('ai.stateCaptured')"
          @click="showAi = true"
        >✦ {{ t('editor.stateBadge') }}</button>
      </div>

      <div class="modes">
        <button :class="{ active: viewMode === 'source' }" @click="viewMode = 'source'">{{ t('editor.source') }}</button>
        <button :class="{ active: viewMode === 'split' }" @click="viewMode = 'split'">{{ t('editor.split') }}</button>
        <button :class="{ active: viewMode === 'preview' }" @click="viewMode = 'preview'">{{ t('editor.preview') }}</button>
      </div>

      <div class="row spacer">
        <label class="toggle" :title="t('editor.interactive')">
          <input type="checkbox" :checked="render.allowScripts" @change="toggleRender('allowScripts')" />
          JS
        </label>
        <label class="toggle" :title="t('editor.external')">
          <input type="checkbox" :checked="render.allowExternal" @change="toggleRender('allowExternal')" />
          CDN
        </label>
        <button class="ghost" @click="openInBrowser" :title="t('editor.openInBrowser')">↗</button>
        <button
          class="ghost icon-btn"
          :class="{ 'agent-warn': !agentReady }"
          :title="(agent.label || t('settings.open'))"
          @click="settingsOpen = true"
        >⚙</button>
        <button class="ghost" @click="rename">{{ t('editor.rename') }}</button>
        <button class="danger" @click="del">{{ t('editor.delete') }}</button>
        <button class="primary" :disabled="!dirty || saving" @click="save">
          {{ saving ? t('editor.saving') : t('editor.save') }}
        </button>
        <button
          v-if="viewMode === 'preview' || viewMode === 'split'"
          class="ghost"
          :class="{ active: editMode }"
          @click="toggleEditMode"
          :title="editMode ? t('editor.editModeActive') : t('editor.editModeInactive')"
        >
          {{ editMode ? '✓ ' + t('editor.editing') : '✎ ' + t('editor.edit') }}
        </button>
        <button class="ghost icon-btn" @click="showAi = !showAi" title="AI">✦</button>
      </div>
    </header>

    <SettingsModal v-model="settingsOpen" @saved="onAgentSaved" />
    <ContextPicker v-model="ctxOpen" :path="currentPath" @changed="onCtxChanged" />

    <!-- Edit element modal -->
    <div v-if="editingElement" class="modal-overlay" @click.self="cancelEdit">
      <div class="edit-modal">
        <h3>{{ t('editor.editElement') }}</h3>
        <p class="edit-hint">{{ t('editor.editHint', { tag: editingElement.tagName }) }}</p>
        <textarea
          ref="editTextarea"
          v-model="editingElement.text"
          class="edit-textarea"
          rows="5"
          @keydown.meta.enter="applyEdit"
          @keydown.ctrl.enter="applyEdit"
          @keydown.esc="cancelEdit"
        ></textarea>
        <div class="edit-actions">
          <button class="ghost" @click="cancelEdit">{{ t('common.cancel') }}</button>
          <button class="primary" @click="applyEdit">{{ t('editor.apply') }}</button>
        </div>
      </div>
    </div>

    <div class="body">
      <!-- file tree -->
      <aside v-show="showTree" class="sidebar scroll">
        <FileTree
          :nodes="tree?.children || []"
          :active-path="currentPath"
          :open-set="openSet"
          @select="selectDoc"
          @toggle="toggleFolder"
          @delete="deleteFromTree"
          @rename="renameFromTree"
        />
      </aside>

      <!-- center: source / preview / split -->
      <main class="center">
        <div v-show="viewMode === 'source' || viewMode === 'split'" class="pane editor-pane" :class="{ half: viewMode === 'split' }">
          <HtmlEditor v-model="editorHtml" @save="save" />
        </div>
        <div v-show="viewMode === 'preview' || viewMode === 'split'" class="pane preview-pane" :class="{ half: viewMode === 'split' }">
          <SandboxPreview
            :html="editorHtml"
            :settings="render"
            :pick-mode="pickMode"
            :edit-mode="editMode"
            @state="onIfaceState"
            @to-agent="onIfaceToAgent"
            @event="onIfaceEvent"
            @pick="onPick"
            @pick-cancel="pickMode = false"
            @edit="onEdit"
            @edit-cancel="editMode = false"
          />
        </div>
      </main>

      <!-- AI panel -->
      <aside v-show="showAi" class="ai-side" :style="{ width: aiWidth + 'px', minWidth: aiWidth + 'px' }">
        <div class="ai-resizer" :title="t('editor.dragWidth')" @mousedown.prevent="startAiResize"></div>
        <AiPanel
          ref="aiPanelRef"
          :current-html="editorHtml"
          :path="currentPath"
          :interface-state="interfaceState"
          :picked-element="pickedElement"
          :pick-mode="pickMode"
          :context-count="ctxCount"
          :disabled="!agentReady"
          :disabled-reason="agent.label || t('home.llmMissing')"
          @apply="onAiApply"
          @clear-state="interfaceState = null"
          @toggle-pick="togglePick"
          @clear-picked="pickedElement = null"
          @open-context="ctxOpen = true"
        />
      </aside>
    </div>

    <div v-if="aiResizing" class="resize-overlay"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, defineAsyncComponent, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import FileTree from '@/components/FileTree.vue'
import HtmlEditor from '@/components/HtmlEditor.vue'
// TipTap + extensions weigh ~800 KB minified; load only when the user actually
// enters Blocks mode so the source/split/preview path stays small.
const BlockEditor = defineAsyncComponent(() => import('@/components/BlockEditor.vue'))
import SandboxPreview from '@/components/SandboxPreview.vue'
import AiPanel from '@/components/AiPanel.vue'
import SettingsModal from '@/components/SettingsModal.vue'
import ContextPicker from '@/components/ContextPicker.vue'
import { getDocument, saveDocument, getTree, deleteDocument, renameDocument } from '@/api/documents'
import { getWorkspace, setRenderSettings } from '@/api/workspace'
import { getContextPicks } from '@/api/context'
import { pushToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const currentPath = computed(() => route.query.path || '')
const doc = ref(null)
const editorHtml = ref('')
const savedHtml = ref('')
const saving = ref(false)
const viewMode = ref('split')
const showTree = ref(true)
const showAi = ref(true)
const interfaceState = ref(null) // last state the rendered doc reported via window.phial
const pickedElement = ref(null)  // element captured from the preview via "选元素"
const pickMode = ref(false)
const editMode = ref(false)      // edit mode: click elements in preview to edit their text
const editingElement = ref(null) // element being edited { selector, text, tagName }
const editTextarea = ref(null)
const aiPanelRef = ref(null)

const tree = ref(null)
const openSet = ref(new Set())
const render = ref({ allowScripts: true, allowExternal: false })
const agent = ref({ label: '', ready: true })
const settingsOpen = ref(false)
const ctxOpen = ref(false)
const ctxCount = ref(0)   // total picked files for the current doc (chip badge)

// resizable AI panel
const AI_MIN = 300
const AI_MAX = 760
const clampAiWidth = (w) => Math.max(AI_MIN, Math.min(AI_MAX, Number(w) || 380))
const aiWidth = ref(clampAiWidth(localStorage.getItem('phial.aiWidth')))
const aiResizing = ref(false)
let aiResizeStart = null

const dirty = computed(() => editorHtml.value !== savedHtml.value)
const agentReady = computed(() => agent.value.ready !== false)

async function loadWorkspace() {
  try {
    const ws = await getWorkspace()
    if (ws.render) render.value = { ...render.value, ...ws.render }
    if (ws.agent) agent.value = ws.agent
  } catch (e) {
    /* non-fatal */
  }
}

function onAgentSaved(active) {
  if (active) agent.value = active
}

async function loadTree() {
  try {
    tree.value = await getTree()
    // auto-expand folders on the path of the current doc
    const parts = currentPath.value.split('/')
    let acc = ''
    parts.slice(0, -1).forEach((p) => {
      acc = acc ? acc + '/' + p : p
      openSet.value.add(acc)
    })
    openSet.value = new Set(openSet.value)
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

async function loadDoc() {
  if (!currentPath.value) {
    goHome()
    return
  }
  try {
    const d = await getDocument(currentPath.value)
    doc.value = d
    editorHtml.value = d.html
    savedHtml.value = d.html
    interfaceState.value = null
    pickedElement.value = null
    pickMode.value = false
    refreshCtxCount()
  } catch (e) {
    pushToast(e.message, 'error')
    goHome()
  }
}

// Fetches just the picks so the chip shows the right number even before the
// drawer is opened. Cheap: settings.json read.
async function refreshCtxCount() {
  if (!currentPath.value) {
    ctxCount.value = 0
    return
  }
  try {
    const picks = await getContextPicks(currentPath.value)
    ctxCount.value = countPicks(picks)
  } catch {
    ctxCount.value = 0
  }
}

function countPicks(picks) {
  let n = (picks?.docs || []).length
  for (const f of (picks?.folders || [])) n += (f.picks || []).length
  return n
}

function onCtxChanged(picks) {
  ctxCount.value = countPicks(picks)
}

async function save() {
  if (!dirty.value || saving.value) return
  saving.value = true
  try {
    const d = await saveDocument(currentPath.value, editorHtml.value)
    savedHtml.value = editorHtml.value
    if (doc.value) doc.value.title = d.title
    pushToast(t('editor.saved'), 'success', 1500)
    loadTree()
  } catch (e) {
    pushToast(e.message, 'error')
  } finally {
    saving.value = false
  }
}

function selectDoc(path) {
  if (path === currentPath.value) return
  if (dirty.value && !window.confirm(t('editor.unsaved') + ' — ' + t('common.confirm') + '?')) return
  router.push({ name: 'editor', query: { path } })
}

function toggleFolder(path) {
  if (openSet.value.has(path)) openSet.value.delete(path)
  else openSet.value.add(path)
  openSet.value = new Set(openSet.value)
}

async function toggleRender(key) {
  const next = { ...render.value, [key]: !render.value[key] }
  render.value = next
  try {
    await setRenderSettings({ [key]: next[key] })
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

async function rename() {
  const dst = window.prompt(t('editor.renamePrompt'), currentPath.value)
  if (!dst || dst === currentPath.value) return
  try {
    const d = await renameDocument(currentPath.value, dst)
    await loadTree()
    router.replace({ name: 'editor', query: { path: d.path } })
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

async function del() {
  if (!window.confirm(t('editor.confirmDelete', { name: doc.value?.title || currentPath.value }))) return
  try {
    await deleteDocument(currentPath.value)
    pushToast(t('editor.delete') + ' ✓', 'success')
    goHome()
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

// --- file-tree row actions (any doc/folder, not just the open one) -------
function isOpenDocOrAncestor(path) {
  return currentPath.value === path || currentPath.value.startsWith(path + '/')
}

async function deleteFromTree(node) {
  const isDir = node.type === 'dir'
  const msg = isDir
    ? t('editor.confirmDeleteDir', { name: node.name })
    : t('editor.confirmDelete', { name: node.title || node.name })
  if (!window.confirm(msg)) return
  try {
    await deleteDocument(node.path)
    pushToast(t('editor.delete') + ' ✓', 'success')
    if (isOpenDocOrAncestor(node.path)) {
      goHome()
      return
    }
    await loadTree()
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

async function renameFromTree(node) {
  const dst = window.prompt(t('editor.renamePrompt'), node.path)
  if (!dst || dst === node.path) return
  try {
    const d = await renameDocument(node.path, dst)
    await loadTree()
    if (currentPath.value === node.path) router.replace({ name: 'editor', query: { path: d.path } })
  } catch (e) {
    pushToast(e.message, 'error')
  }
}

function openInBrowser() {
  window.open('/api/documents/raw?path=' + encodeURIComponent(currentPath.value), '_blank')
}

// AI result lands straight in the editor (dirty, not saved — review & Cmd+S).
function onAiApply(html) {
  if (html == null || html === editorHtml.value) return
  editorHtml.value = html
  interfaceState.value = null
  // Surface the result: from pure source view, show the preview alongside.
  // Blocks view now handles interactive content natively via widget blocks,
  // so no special-case fallback needed.
  if (viewMode.value === 'source') viewMode.value = 'split'
}

// --- pick element from the preview ---------------------------------------
function togglePick() {
  pickMode.value = !pickMode.value
  // make sure the user can see the preview when picking
  if (pickMode.value && viewMode.value === 'source') viewMode.value = 'split'
  // disable edit mode when picking
  if (pickMode.value && editMode.value) editMode.value = false
}
function onPick(data) {
  pickedElement.value = data || null
  pickMode.value = false
  showAi.value = true
  // give focus to the AI prompt so they can immediately type the change
  requestAnimationFrame(() => {
    const ta = document.querySelector('.ai-input textarea')
    if (ta) ta.focus()
  })
}

// --- edit mode: click elements in preview to edit text -------------------
function toggleEditMode() {
  editMode.value = !editMode.value
  // make sure the user can see the preview when editing
  if (editMode.value && viewMode.value === 'source') viewMode.value = 'split'
  // disable pick mode when editing
  if (editMode.value && pickMode.value) pickMode.value = false
}

function onEdit(data) {
  editingElement.value = { ...data }
  editMode.value = false
  // focus the textarea after it's mounted
  nextTick(() => {
    if (editTextarea.value) {
      editTextarea.value.focus()
      editTextarea.value.select()
    }
  })
}

function cancelEdit() {
  editingElement.value = null
  editMode.value = true
}

function applyEdit() {
  if (!editingElement.value) return
  const { selector, text } = editingElement.value
  // Find and replace the text in the HTML
  const parser = new DOMParser()
  const doc = parser.parseFromString(editorHtml.value, 'text/html')
  const el = doc.querySelector(selector)
  if (el) {
    // Replace only direct text nodes, preserve child elements
    for (let i = el.childNodes.length - 1; i >= 0; i--) {
      const node = el.childNodes[i]
      if (node.nodeType === 3) el.removeChild(node)
    }
    el.insertBefore(doc.createTextNode(text), el.firstChild)
    editorHtml.value = '<!DOCTYPE html>\n' + doc.documentElement.outerHTML
  }
  editingElement.value = null
  editMode.value = true
}

// --- the two-way loop with the rendered document (window.phial) ----------
function onIfaceState(data) {
  interfaceState.value = data
}

function onIfaceToAgent({ text, data }) {
  if (data != null) interfaceState.value = data
  showAi.value = true
  // wait a tick so the AiPanel is mounted/visible before submitting
  requestAnimationFrame(() => aiPanelRef.value?.submitWith(text))
}

function onIfaceEvent({ name }) {
  if (name) pushToast('界面事件: ' + name, 'info', 1800)
}

function startAiResize(e) {
  aiResizeStart = { x: e.clientX, w: aiWidth.value }
  aiResizing.value = true
  window.addEventListener('mousemove', onAiResize)
  window.addEventListener('mouseup', endAiResize)
}
function onAiResize(e) {
  if (!aiResizeStart) return
  aiWidth.value = clampAiWidth(aiResizeStart.w + (aiResizeStart.x - e.clientX))
}
function endAiResize() {
  aiResizeStart = null
  aiResizing.value = false
  window.removeEventListener('mousemove', onAiResize)
  window.removeEventListener('mouseup', endAiResize)
  localStorage.setItem('phial.aiWidth', String(aiWidth.value))
}

function goHome() {
  router.push({ name: 'home' })
}

function beforeUnload(e) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

watch(currentPath, loadDoc)
onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload)
  await loadWorkspace()
  await loadTree()
  await loadDoc()
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  window.removeEventListener('mousemove', onAiResize)
  window.removeEventListener('mouseup', endAiResize)
})
</script>

<style scoped>
.editor-shell { display: flex; flex-direction: column; height: 100%; }

.topbar {
  display: flex; align-items: center; gap: 10px; padding: 7px 12px;
  border-bottom: 1px solid var(--border); background: var(--bg-panel); flex-wrap: nowrap;
}
.icon-btn { padding: 5px 9px; }
.icon-btn.agent-warn { color: #b45309; border-color: #fde68a; background: #fffbeb; }
.doc-id { display: flex; align-items: baseline; gap: 8px; min-width: 0; overflow: hidden; }
.doc-id code { font-family: var(--mono); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dirty { font-size: 11.5px; color: var(--text-dim); white-space: nowrap; }
.dirty.on { color: #b45309; }
.state-pill {
  padding: 2px 8px; font-size: 11.5px; border-radius: 999px; white-space: nowrap;
  border-color: var(--accent-soft); background: var(--accent-soft); color: var(--accent);
}
.state-pill:hover { background: #ddd6fe; }
.modes { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.modes button { border: 0; border-radius: 0; padding: 5px 11px; background: var(--bg-panel); }
.modes button + button { border-left: 1px solid var(--border); }
.modes button.active { background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.spacer { flex: 1; }
.row.spacer { display: flex; align-items: center; gap: 6px; justify-content: flex-end; flex: 1; }
.toggle { display: flex; align-items: center; gap: 3px; font-size: 12px; color: var(--text-dim); user-select: none; }

.body { flex: 1; display: flex; min-height: 0; }
.sidebar { width: 230px; min-width: 230px; border-right: 1px solid var(--border); background: var(--bg); }
.center { flex: 1; display: flex; min-width: 0; }
.pane { min-width: 0; height: 100%; }
.editor-pane { flex: 1; border-right: 1px solid var(--border); }
.preview-pane { flex: 1; display: flex; flex-direction: column; background: #fff; }
.pane.half { flex: 1 1 50%; width: 50%; }
.blocks-pane { flex: 1; display: flex; flex-direction: column; background: var(--bg, #fff); min-width: 0; }
.ai-side { width: 380px; min-width: 380px; border-left: 1px solid var(--border); position: relative; }
.ai-resizer {
  position: absolute; left: -3px; top: 0; bottom: 0; width: 6px; cursor: col-resize; z-index: 6;
}
.ai-resizer:hover { background: var(--accent-soft); }
.resize-overlay { position: fixed; inset: 0; z-index: 998; cursor: col-resize; }

/* Edit modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.edit-modal {
  background: var(--bg-panel, #fff);
  border-radius: 8px;
  padding: 20px;
  width: 90%;
  max-width: 500px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}
.edit-modal h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
}
.edit-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-dim, #6b7280);
}
.edit-textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 6px;
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1.5;
  resize: vertical;
  min-height: 100px;
}
.edit-textarea:focus {
  outline: none;
  border-color: var(--accent, #6d28d9);
}
.edit-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
