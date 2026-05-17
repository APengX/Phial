<template>
  <div v-if="modelValue" class="overlay" @click.self="close">
    <div class="drawer" role="dialog" aria-modal="true">
      <header class="cp-head">
        <strong>{{ t('ctx.title', { path }) }}</strong>
        <button class="ghost x" :title="t('ctx.close')" @click="close">×</button>
      </header>

      <p class="cp-intro muted">{{ t('ctx.intro') }}</p>

      <div v-if="loading" class="cp-loading muted">{{ t('common.loading') }}</div>

      <div v-else class="cp-body scroll">
        <!-- Bound folders -->
        <section class="cp-sec">
          <h3>{{ t('ctx.folders') }}</h3>
          <div v-if="!folders.length" class="cp-empty muted">{{ t('ctx.foldersEmpty') }}</div>

          <div v-for="f in folders" :key="f.path" class="folder">
            <div class="folder-head" @click="toggleFolderOpen(f.path)">
              <span class="chev" :class="{ open: isOpen(f.path) }" aria-hidden="true">▸</span>
              <span class="f-name">{{ f.name }}</span>
              <code class="f-path">{{ f.path }}</code>
              <span class="f-stat" :class="{ missing: f.missing }">
                <template v-if="f.missing">{{ t('ctx.folderMissing') }}</template>
                <template v-else>{{ pickedFor(f.path).size }} / {{ treeFor(f.path).length }}</template>
              </span>
              <span class="spacer"></span>
              <button
                v-if="!f.missing && treeFor(f.path).length"
                class="ghost mini"
                :title="t('ctx.selectAll')"
                @click.stop="selectAllInFolder(f.path)"
              >✓✓</button>
              <button
                v-if="!f.missing && pickedFor(f.path).size"
                class="ghost mini"
                :title="t('ctx.clearAll')"
                @click.stop="clearFolder(f.path)"
              >×</button>
            </div>

            <div v-if="isOpen(f.path) && !f.missing" class="files-wrap">
              <div v-if="treeLoadingFor(f.path)" class="empty-line muted">{{ t('common.loading') }}</div>
              <div v-else-if="!treeFor(f.path).length" class="empty-line muted">{{ t('ctx.noFiles') }}</div>
              <ul v-else class="tree-ul">
                <ContextTreeNode
                  v-for="node in treeNodesFor(f.path)"
                  :key="node.path || node.rel"
                  :node="node"
                  :picks="pickedFor(f.path)"
                  :open-set="dirOpenFor(f.path)"
                  @toggle-file="onToggleFile(f.path, $event)"
                  @toggle-dir="onToggleDir(f.path, $event)"
                  @toggle-open="onToggleDirOpen(f.path, $event)"
                />
              </ul>
            </div>
          </div>
        </section>

        <!-- Workspace cross-doc picks -->
        <section class="cp-sec">
          <h3>{{ t('ctx.workspaceDocs') }}</h3>
          <div v-if="!workspaceDocs.length" class="cp-empty muted">{{ t('ctx.workspaceDocsEmpty') }}</div>
          <ul v-else class="files flat">
            <li
              v-for="d in workspaceDocs"
              :key="d.rel"
              class="file-row"
              :class="{ on: docsSet.has(d.rel) }"
            >
              <label>
                <input
                  type="checkbox"
                  :checked="docsSet.has(d.rel)"
                  @change="toggleDoc(d.rel, $event.target.checked)"
                />
                <span class="file-name">
                  <span class="doc-title">{{ d.title || d.rel }}</span>
                  <code v-if="d.title && d.title !== d.rel" class="doc-rel">{{ d.rel }}</code>
                </span>
                <span class="file-size muted">{{ fmtKb(d.size) }}</span>
              </label>
            </li>
          </ul>
        </section>
      </div>

      <footer class="cp-foot">
        <span class="muted">
          {{ t('ctx.summary', { files: totalPickedFiles, kb: totalKb }) }}
        </span>
        <span class="spacer"></span>
        <button class="primary" @click="close">{{ t('ctx.close') }}</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
// ContextPicker — opens from the AI panel via a chip. Lets the user tick
// individual files (under any bound folder) and other workspace .html docs
// to splice into the next AI prompt. Picks are persisted per doc; an open
// drawer reflects the saved state. Each toggle is PUT immediately (the
// settings file is tiny) so closing the drawer never loses changes.

import { ref, reactive, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  listContextFolders,
  getContextPicks,
  putContextPicks,
  listContextTree,
  listWorkspaceDocs
} from '@/api/context'
import { pushToast } from '@/composables/useToast'
import ContextTreeNode from '@/components/ContextTreeNode.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  path: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'changed'])
const { t } = useI18n()

const loading = ref(false)
// folder summaries (path / name / fileCount / pickedCount / missing)
const folders = ref([])
// flat trees per folder: { [abs]: [{rel,size}] } — used to compute sizes.
const trees = reactive({})
// hierarchical trees per folder: { [abs]: [<rootNodes>] } — derived from `trees`.
// Each dir node carries `allFiles` (rels under it) so subtree toggles are O(k).
const treeNodes = reactive({})
// open state for the folder *card* itself: { [abs]: bool }
const openMap = reactive({})
// open state for subdirectories *inside* a folder: { [abs]: Set<subPath> }
const dirOpenMap = reactive({})
// per-folder loading flag (lazy-load trees on first open)
const treeLoading = reactive({})
// per-folder pick sets: { [abs]: Set<fileRel> }
const folderPicks = reactive({})
// workspace docs and current doc picks
const workspaceDocs = ref([])
const docsSet = reactive(new Set())

const totalPickedFiles = computed(() => {
  let n = docsSet.size
  for (const k of Object.keys(folderPicks)) n += folderPicks[k].size
  return n
})
const totalKb = computed(() => {
  let bytes = 0
  for (const f of folders.value) {
    const picks = folderPicks[f.path]
    if (!picks || !picks.size) continue
    const sizes = Object.fromEntries((trees[f.path] || []).map((x) => [x.rel, x.size]))
    for (const r of picks) bytes += sizes[r] || 0
  }
  for (const d of workspaceDocs.value) {
    if (docsSet.has(d.rel)) bytes += d.size || 0
  }
  return Math.round(bytes / 1024)
})

function pickedFor(abs) {
  if (!folderPicks[abs]) folderPicks[abs] = new Set()
  return folderPicks[abs]
}
function treeFor(abs) { return trees[abs] || [] }
function treeNodesFor(abs) { return treeNodes[abs] || [] }
function treeLoadingFor(abs) { return !!treeLoading[abs] }
function isOpen(abs) { return !!openMap[abs] }
function dirOpenFor(abs) {
  if (!dirOpenMap[abs]) dirOpenMap[abs] = new Set()
  return dirOpenMap[abs]
}

// Groups a flat list of `{rel, size}` into a nested `{type:'dir'|'file', ...}`
// tree. Each dir node gets `allFiles` (rels under it, recursive) precomputed
// so the tri-state checkbox and "select-whole-subtree" toggle are O(k).
function buildTree(flatFiles) {
  const root = { type: 'dir', name: '', path: '', children: [], allFiles: [] }
  const dirs = new Map([['', root]])
  for (const f of flatFiles) {
    const parts = f.rel.split('/')
    let cur = root
    let acc = ''
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? acc + '/' + parts[i] : parts[i]
      let child = dirs.get(acc)
      if (!child) {
        child = { type: 'dir', name: parts[i], path: acc, children: [], allFiles: [] }
        cur.children.push(child)
        dirs.set(acc, child)
      }
      cur = child
    }
    cur.children.push({
      type: 'file',
      name: parts[parts.length - 1],
      rel: f.rel,
      size: f.size,
      kind: f.kind || 'text'
    })
  }
  // Sort: dirs first, then files; both alphabetical. Also fill allFiles.
  function finalize(n) {
    n.children.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const c of n.children) {
      if (c.type === 'dir') {
        finalize(c)
        n.allFiles.push(...c.allFiles)
      } else {
        n.allFiles.push(c.rel)
      }
    }
  }
  finalize(root)
  return root.children
}

function fmtKb(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  return (bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0) + ' KB'
}

function close() { emit('update:modelValue', false) }

// ---- open / load -------------------------------------------------------
watch(() => props.modelValue, async (open) => {
  if (!open || !props.path) return
  loading.value = true
  // Reset between opens so a stale folder/picks set from another doc never
  // bleeds in.
  folders.value = []
  Object.keys(trees).forEach((k) => delete trees[k])
  Object.keys(treeNodes).forEach((k) => delete treeNodes[k])
  Object.keys(openMap).forEach((k) => delete openMap[k])
  Object.keys(dirOpenMap).forEach((k) => delete dirOpenMap[k])
  Object.keys(treeLoading).forEach((k) => delete treeLoading[k])
  Object.keys(folderPicks).forEach((k) => delete folderPicks[k])
  docsSet.clear()
  workspaceDocs.value = []
  try {
    const [{ folders: fList }, picks, { docs }] = await Promise.all([
      listContextFolders(props.path),
      getContextPicks(props.path),
      listWorkspaceDocs(props.path)
    ])
    folders.value = fList || []
    workspaceDocs.value = docs || []
    // seed picks
    for (const f of (picks.folders || [])) {
      folderPicks[f.path] = new Set(f.picks || [])
    }
    for (const d of (picks.docs || [])) docsSet.add(d)
    // auto-open folders that already have picks so the user sees them
    for (const f of folders.value) {
      if (f.missing) continue
      if (folderPicks[f.path]?.size) {
        openMap[f.path] = true
        loadTree(f.path)
      }
    }
  } catch (e) {
    pushToast(t('ctx.loadTreeFailed', { msg: e.message }), 'error')
  } finally {
    loading.value = false
  }
})

async function loadTree(abs) {
  if (trees[abs] || treeLoading[abs]) return
  treeLoading[abs] = true
  try {
    const { files } = await listContextTree(props.path, abs)
    trees[abs] = files || []
    treeNodes[abs] = buildTree(trees[abs])
    // Auto-open any dir that contains an already-picked file so the user can
    // see what's checked instead of an all-collapsed view.
    autoOpenForPicks(abs)
  } catch (e) {
    pushToast(t('ctx.loadTreeFailed', { msg: e.message }), 'error')
    trees[abs] = []
    treeNodes[abs] = []
  } finally {
    treeLoading[abs] = false
  }
}

function autoOpenForPicks(abs) {
  const picks = folderPicks[abs]
  if (!picks || !picks.size) return
  const opens = dirOpenFor(abs)
  for (const rel of picks) {
    const parts = rel.split('/')
    let acc = ''
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? acc + '/' + parts[i] : parts[i]
      opens.add(acc)
    }
  }
}

function toggleFolderOpen(abs) {
  openMap[abs] = !openMap[abs]
  if (openMap[abs]) loadTree(abs)
}

// ---- mutate + persist --------------------------------------------------
let saveTimer = null
function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  // Small debounce so a "select all" of 50 files turns into one PUT, not 50.
  saveTimer = setTimeout(persist, 150)
}

async function persist() {
  saveTimer = null
  const payload = {
    folders: folders.value
      .filter((f) => !f.missing || folderPicks[f.path]?.size)
      .map((f) => ({ path: f.path, picks: [...(folderPicks[f.path] || [])] })),
    docs: [...docsSet]
  }
  try {
    const fresh = await putContextPicks(props.path, payload)
    // The server may have dropped invalid entries (e.g. workspace doc
    // disappeared); reflect that back into our local state.
    docsSet.clear()
    for (const d of (fresh.docs || [])) docsSet.add(d)
    // Re-sync folder picks too — the server canonicalizes them.
    for (const f of (fresh.folders || [])) {
      folderPicks[f.path] = new Set(f.picks || [])
    }
    emit('changed', fresh)
  } catch (e) {
    pushToast(t('ctx.saveFailed', { msg: e.message }), 'error')
  }
}

// Single-file toggle from a leaf in the tree.
function onToggleFile(abs, { rel, on }) {
  const set = pickedFor(abs)
  if (on) set.add(rel); else set.delete(rel)
  scheduleSave()
}

// Directory checkbox: add/remove every file under it. Uses the precomputed
// `allFiles` so this is O(k) regardless of tree depth.
function onToggleDir(abs, { node, on }) {
  const set = pickedFor(abs)
  if (on) {
    for (const rel of node.allFiles) set.add(rel)
  } else {
    for (const rel of node.allFiles) set.delete(rel)
  }
  scheduleSave()
}

function onToggleDirOpen(abs, subPath) {
  const opens = dirOpenFor(abs)
  if (opens.has(subPath)) opens.delete(subPath)
  else opens.add(subPath)
}

function selectAllInFolder(abs) {
  const set = pickedFor(abs)
  for (const f of treeFor(abs)) set.add(f.rel)
  scheduleSave()
}

function clearFolder(abs) {
  folderPicks[abs] = new Set()
  scheduleSave()
}

function toggleDoc(rel, on) {
  if (on) docsSet.add(rel); else docsSet.delete(rel)
  scheduleSave()
}
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0; background: rgba(15, 19, 28, 0.4); z-index: 500;
  display: flex; justify-content: flex-end;
}
.drawer {
  background: var(--bg-panel); width: 520px; max-width: 100%;
  display: flex; flex-direction: column; box-shadow: -16px 0 48px rgba(0, 0, 0, 0.18);
}
.cp-head {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
}
.cp-head strong { flex: 1; font-size: 14px; }
.x { padding: 1px 8px; font-size: 1.1rem; line-height: 1; }

.cp-intro { padding: 10px 16px 0; font-size: 12.5px; line-height: 1.5; }
.cp-loading { padding: 24px 16px; }
.cp-body { flex: 1; overflow: auto; padding: 10px 16px 18px; }
.cp-sec { margin-top: 12px; }
.cp-sec h3 {
  font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--text-dim); margin: 0 0 8px;
}
.cp-empty { font-size: 12.5px; padding: 6px 0 4px; }

.folder { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.folder-head {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px; cursor: pointer; user-select: none;
  flex-wrap: wrap;
}
.folder-head:hover { background: var(--bg-soft); }
.chev { color: var(--text-dim); transition: transform 0.12s; font-size: 12px; }
.chev.open { transform: rotate(90deg); }
.f-name { font-weight: 500; }
.f-path { font-family: var(--mono); font-size: 11.5px; color: var(--text-dim); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.f-stat { font-size: 11.5px; color: var(--text-dim); white-space: nowrap; }
.f-stat.missing { color: #b45309; }
.spacer { flex: 0 0 4px; }
.mini { padding: 1px 7px; font-size: 11.5px; }

.files-wrap {
  border-top: 1px solid var(--border); background: var(--bg-soft);
  padding: 4px 0;
}
.tree-ul { list-style: none; margin: 0; padding: 0; }
.empty-line { padding: 6px 14px; font-size: 12.5px; }

.files { list-style: none; margin: 0; padding: 0; }
.files.flat { background: transparent; padding: 0; }
.files.flat .file-row {
  padding: 4px 10px; border: 1px solid var(--border); border-radius: 7px; margin-bottom: 5px; background: var(--bg-panel);
}
.files.flat .file-row.on { border-color: var(--accent); background: var(--accent-soft); }
.files.flat .file-row label {
  display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 12.5px; line-height: 1.45;
}
.files.flat .file-row input[type="checkbox"] { flex: none; margin: 0; }
.file-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { font-size: 11px; white-space: nowrap; }
.doc-title { font-weight: 500; margin-right: 6px; }
.doc-rel { font-family: var(--mono); font-size: 11px; color: var(--text-dim); }

.cp-foot {
  display: flex; align-items: center; gap: 10px;
  padding: 11px 16px; border-top: 1px solid var(--border);
}
.cp-foot .spacer { flex: 1; }
</style>
