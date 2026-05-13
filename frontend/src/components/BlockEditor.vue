<template>
  <div class="block-editor-host">
    <EditorContent v-if="editor" :editor="editor" class="be-content" />

    <!-- Drag handle that follows the hovered block. The slot is the visible
         "⋮⋮" pill; clicking it opens BlockHandleMenu next to it. Dragging it
         reorders the block (TipTap handles the drag wiring itself). -->
    <DragHandle
      v-if="editor"
      :editor="editor"
      :on-node-change="onHoverNodeChange"
      class="be-drag-handle-wrap"
    >
      <button
        type="button"
        class="be-handle"
        :title="t('blocks.handleTip')"
        @click="openHandleMenu($event)"
        @mousedown.stop
      >⋮⋮</button>
    </DragHandle>

    <BlockHandleMenu
      :open="handleMenu.open"
      :top="handleMenu.top"
      :left="handleMenu.left"
      @turn-into="onTurnInto"
      @duplicate="onDuplicateBlock"
      @delete="onDeleteBlock"
      @close="handleMenu.open = false"
    />

    <SlashMenuList
      v-if="slash.open"
      :items="slash.items"
      :active-index="slash.activeIndex"
      :top="slash.top"
      :left="slash.left"
      :query="slash.query"
      @pick="onSlashPick"
      @hover="(i) => (slash.activeIndex = i)"
    />
  </div>
</template>

<script setup>
// Notion-ish visual block editor for Phial documents.
//
// Phial docs are *full* HTML documents (<!doctype><html><head><style>…</head>
// <body>…</body></html>). TipTap can only edit body-level content, and silently
// drops elements that aren't in its schema. So we split the incoming HTML into
// an "envelope" (everything up to and including `<body…>`, plus `</body>…`)
// and a "body" fragment that goes into the editor. On every update we glue the
// envelope back around the new body and emit the full doc — so the <head>
// (title, charset, <style>) survives block editing untouched.
//
// PR 2 added: slash command menu (`/`), drag handle with per-block menu
// (Turn into / Duplicate / Delete), markdown shortcuts (inherited from
// StarterKit's input rules — `# `, `> `, `- `, `1. `, ``` ```, `---`).
//
// Docs containing `<script>` are caught upstream in EditorView and never
// mounted into this component; the widget-block work in PR 3 will resolve
// that.

import { ref, reactive, watch, onMounted, onBeforeUnmount } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import Placeholder from '@tiptap/extension-placeholder'
import { DragHandle } from '@tiptap/extension-drag-handle-vue-3'
import { useI18n } from 'vue-i18n'

import { SlashCommands } from './blockEditor/slashCommands'
import SlashMenuList from './blockEditor/SlashMenuList.vue'
import BlockHandleMenu from './blockEditor/BlockHandleMenu.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

// ─── envelope round-trip ──────────────────────────────────────────────────
let envelope = null
let suppressUpdate = false

function splitDoc(html) {
  if (!html) return { prefix: '', body: '', suffix: '' }
  const openMatch = html.match(/<body\b[^>]*>/i)
  const closeIdx = openMatch ? html.lastIndexOf('</body>') : -1
  if (!openMatch || closeIdx < 0 || closeIdx < openMatch.index + openMatch[0].length) {
    return { prefix: '', body: html, suffix: '' }
  }
  const bodyStart = openMatch.index + openMatch[0].length
  return {
    prefix: html.slice(0, bodyStart),
    body: html.slice(bodyStart, closeIdx),
    suffix: html.slice(closeIdx),
  }
}
function joinDoc(prefix, body, suffix) {
  if (!prefix && !suffix) return body
  return prefix + body + suffix
}

// ─── slash menu state ─────────────────────────────────────────────────────
// Reactive shape the SlashMenuList paints. The TipTap suggestion plugin
// drives this from its render hooks (see slashRender below).
const slash = reactive({
  open: false,
  items: [],
  query: '',
  activeIndex: 0,
  top: 0,
  left: 0,
  // ProseMirror range of the `/query` that triggered the menu — passed to
  // the chosen item's command so it can delete it before inserting a block.
  range: null,
})

// Item table. Each item's `command({editor, range})` deletes the `/query`
// text first, then mutates the block. `keywords` (lowercase) drives the
// fuzzy filter when the user types after `/`.
function buildSlashItems() {
  return [
    {
      key: 'paragraph', icon: '¶', title: t('blocks.items.paragraph'),
      hint: t('blocks.hints.paragraph'), keywords: 'text paragraph p body',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).setParagraph().run(),
    },
    {
      key: 'h1', icon: 'H₁', title: t('blocks.items.h1'), hint: '#',
      keywords: 'heading h1 title big 标题',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).setHeading({ level: 1 }).run(),
    },
    {
      key: 'h2', icon: 'H₂', title: t('blocks.items.h2'), hint: '##',
      keywords: 'heading h2 sub 副标题',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).setHeading({ level: 2 }).run(),
    },
    {
      key: 'h3', icon: 'H₃', title: t('blocks.items.h3'), hint: '###',
      keywords: 'heading h3 sub 副标题',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).setHeading({ level: 3 }).run(),
    },
    {
      key: 'ul', icon: '•', title: t('blocks.items.ul'), hint: '- ',
      keywords: 'bullet unordered list ul 列表 项',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).toggleBulletList().run(),
    },
    {
      key: 'ol', icon: '1.', title: t('blocks.items.ol'), hint: '1. ',
      keywords: 'ordered numbered list ol 列表',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).toggleOrderedList().run(),
    },
    {
      key: 'task', icon: '☐', title: t('blocks.items.task'), hint: '[ ]',
      keywords: 'todo task checklist check 待办',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).toggleTaskList().run(),
    },
    {
      key: 'quote', icon: '❝', title: t('blocks.items.quote'), hint: '> ',
      keywords: 'quote blockquote 引用',
      // Blockquote is a *wrapping* node (contains paragraphs), so we use the
      // dedicated toggle — `setNode('blockquote')` would silently no-op.
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).toggleBlockquote().run(),
    },
    {
      key: 'code', icon: '⌨', title: t('blocks.items.code'), hint: '``` ',
      keywords: 'code block monospace 代码',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).toggleCodeBlock().run(),
    },
    {
      key: 'divider', icon: '—', title: t('blocks.items.divider'), hint: '---',
      keywords: 'divider hr horizontal rule line 分割线',
      command: ({ editor, range }) =>
        editor.chain().focus().deleteRange(range).setHorizontalRule().run(),
    },
    {
      key: 'image', icon: '🖼', title: t('blocks.items.image'), hint: 'URL',
      keywords: 'image img picture photo 图',
      command: ({ editor, range }) => {
        const src = window.prompt(t('blocks.imagePrompt'))
        editor.chain().focus().deleteRange(range).run()
        if (src) editor.chain().focus().setImage({ src }).run()
      },
    },
  ]
}

function filterSlashItems(query) {
  const all = buildSlashItems()
  const q = (query || '').toLowerCase().trim()
  if (!q) return all
  return all.filter((it) =>
    it.title.toLowerCase().includes(q) ||
    (it.hint || '').toLowerCase().includes(q) ||
    it.keywords.includes(q) ||
    it.key.includes(q)
  )
}

// Suggestion render lifecycle. The plugin calls onStart when `/` is typed,
// onUpdate as the query changes, onKeyDown for every key (we intercept
// arrows/Enter/Escape), and onExit when it ends (selection moved, char
// deleted, etc.).
const slashRender = () => {
  // Position helper: anchor menu under the caret with a small offset.
  const place = (rect) => {
    if (!rect) return
    const GAP = 6
    const W = 280
    const H_MAX = 320
    const vw = window.innerWidth
    const vh = window.innerHeight
    let left = rect.left
    let top = rect.bottom + GAP
    if (left + W > vw - 8) left = vw - W - 8
    if (top + H_MAX > vh - 8) top = Math.max(8, rect.top - H_MAX - GAP)
    slash.top = top
    slash.left = left
  }

  return {
    onStart: (p) => {
      slash.open = true
      slash.items = p.items
      slash.query = p.query
      slash.activeIndex = 0
      slash.range = p.range
      place(p.clientRect?.())
    },
    onUpdate: (p) => {
      slash.items = p.items
      slash.query = p.query
      // Clamp the cursor — items shrunk because of filtering.
      if (slash.activeIndex >= p.items.length) slash.activeIndex = Math.max(0, p.items.length - 1)
      slash.range = p.range
      place(p.clientRect?.())
    },
    onKeyDown: (p) => {
      if (!slash.open) return false
      const k = p.event.key
      if (k === 'ArrowDown') {
        if (slash.items.length) slash.activeIndex = (slash.activeIndex + 1) % slash.items.length
        return true
      }
      if (k === 'ArrowUp') {
        if (slash.items.length)
          slash.activeIndex = (slash.activeIndex - 1 + slash.items.length) % slash.items.length
        return true
      }
      if (k === 'Enter' || k === 'Tab') {
        const item = slash.items[slash.activeIndex]
        if (item) {
          // Hand off to suggestion's command runner — this calls the
          // top-level command in slashCommands.js with this item as `props`.
          p.command(item)
        }
        return true
      }
      if (k === 'Escape') {
        slash.open = false
        return true
      }
      return false
    },
    onExit: () => {
      slash.open = false
    },
  }
}

function onSlashPick(i) {
  const item = slash.items[i]
  if (!item || !editor.value || !slash.range) return
  item.command({ editor: editor.value, range: slash.range })
  slash.open = false
}

// ─── drag handle / block menu state ───────────────────────────────────────
// DragHandle reports the currently hovered block via onNodeChange. We store
// it so the block menu (Turn into / Duplicate / Delete) knows what to act on.
const hovered = ref({ node: null, pos: -1 })
// `target` is the *captured* hover at menu-open time. Once the menu is open,
// mousing through the doc to reach the menu would otherwise drift `hovered`
// onto a different block and the menu would act on the wrong target.
const handleMenu = reactive({ open: false, top: 0, left: 0, target: null })

function onHoverNodeChange({ node, pos }) {
  hovered.value = { node, pos: pos ?? -1 }
  // A scroll / mouse move that re-targets a different block should close any
  // open block menu — it would otherwise act on the wrong target.
  if (handleMenu.open) {
    handleMenu.open = false
    handleMenu.target = null
  }
}

function openHandleMenu(ev) {
  if (hovered.value.pos < 0) return
  const r = ev.currentTarget.getBoundingClientRect()
  handleMenu.top = r.bottom + 4
  handleMenu.left = r.left
  handleMenu.target = { ...hovered.value }   // freeze the block we're acting on
  handleMenu.open = true
  // Click anywhere outside the menu closes it.
  const off = (e) => {
    if (e.target.closest('.blk-menu')) return
    handleMenu.open = false
    handleMenu.target = null
    window.removeEventListener('mousedown', off, true)
  }
  setTimeout(() => window.addEventListener('mousedown', off, true), 0)
}

function withTargetNode(fn) {
  const ed = editor.value
  const target = handleMenu.target
  if (!ed || !target || target.pos < 0 || !target.node) return
  fn(ed, target.pos, target.node)
  handleMenu.open = false
  handleMenu.target = null
}

function onTurnInto(key) {
  withTargetNode((ed, pos) => {
    // Drop the cursor inside the block (pos+1 is just after the opening
    // boundary) so wrapping commands like toggleBulletList / toggleBlockquote
    // act on it. Using setNodeSelection here would be wrong for wrappers.
    const chain = ed.chain().focus().setTextSelection(pos + 1)
    switch (key) {
      case 'paragraph': chain.setParagraph().run(); break
      case 'h1': chain.setHeading({ level: 1 }).run(); break
      case 'h2': chain.setHeading({ level: 2 }).run(); break
      case 'h3': chain.setHeading({ level: 3 }).run(); break
      case 'ul': chain.toggleBulletList().run(); break
      case 'ol': chain.toggleOrderedList().run(); break
      case 'task': chain.toggleTaskList().run(); break
      case 'quote': chain.toggleBlockquote().run(); break
      case 'code': chain.toggleCodeBlock().run(); break
    }
  })
}

function onDuplicateBlock() {
  withTargetNode((ed, pos, node) => {
    const after = pos + node.nodeSize
    ed.chain().focus().insertContentAt(after, node.toJSON()).run()
  })
}

function onDeleteBlock() {
  withTargetNode((ed, pos) => {
    ed.chain().focus().setNodeSelection(pos).deleteSelection().run()
  })
}

// ─── editor instance ──────────────────────────────────────────────────────
const editor = useEditor({
  extensions: [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
    }),
    Image.configure({ inline: false, allowBase64: true }),
    TaskList,
    TaskItem.configure({ nested: true }),
    Placeholder.configure({
      placeholder: () => t('blocks.placeholder'),
    }),
    SlashCommands.configure({
      suggestion: {
        items: ({ query }) => filterSlashItems(query),
        render: slashRender,
      },
    }),
  ],
  content: '',
  onUpdate: ({ editor }) => {
    if (suppressUpdate) return
    const body = editor.getHTML()
    const next = joinDoc(envelope?.prefix || '', body, envelope?.suffix || '')
    emit('update:modelValue', next)
  },
  editorProps: {
    handleKeyDown(_view, event) {
      if ((event.metaKey || event.ctrlKey) && event.key === 's' && !event.shiftKey) {
        event.preventDefault()
        emit('save')
        return true
      }
      return false
    },
  },
})

function applyExternal(html) {
  if (!editor.value) return
  const parts = splitDoc(html || '')
  envelope = (parts.prefix || parts.suffix) ? { prefix: parts.prefix, suffix: parts.suffix } : null
  suppressUpdate = true
  editor.value.commands.setContent(parts.body || '<p></p>', { emitUpdate: false })
  queueMicrotask(() => { suppressUpdate = false })
}

onMounted(() => applyExternal(props.modelValue))

watch(
  () => props.modelValue,
  (val) => {
    if (!editor.value) return
    const parts = splitDoc(val || '')
    const currentBody = editor.value.getHTML()
    const same =
      parts.body === currentBody &&
      (envelope?.prefix || '') === (parts.prefix || '') &&
      (envelope?.suffix || '') === (parts.suffix || '')
    if (same) return
    applyExternal(val)
  }
)

onBeforeUnmount(() => editor.value?.destroy())

defineExpose({
  focus: () => editor.value?.commands.focus(),
})
</script>

<style scoped>
.block-editor-host {
  height: 100%;
  overflow: auto;
  background: var(--bg, #fff);
  position: relative;
}
.be-content {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 40px 80px;
}

/* ProseMirror surface — typography tuned to feel like reading a doc. */
:deep(.ProseMirror) {
  outline: none;
  min-height: 100%;
  font-size: 15px;
  line-height: 1.7;
  color: var(--text, #1f2328);
}

:deep(.ProseMirror > * + *) { margin-top: 0.55em; }
:deep(.ProseMirror p) { margin: 0; }
:deep(.ProseMirror h1) { font-size: 1.9em; font-weight: 600; line-height: 1.25; margin: 0.6em 0 0.25em; }
:deep(.ProseMirror h2) { font-size: 1.5em; font-weight: 600; line-height: 1.3;  margin: 0.9em 0 0.25em; }
:deep(.ProseMirror h3) { font-size: 1.2em; font-weight: 600; line-height: 1.35; margin: 0.9em 0 0.2em; }

:deep(.ProseMirror ul),
:deep(.ProseMirror ol) { padding-left: 1.4em; margin: 0; }
:deep(.ProseMirror li > p) { margin: 0; }

:deep(.ProseMirror blockquote) {
  border-left: 3px solid var(--border, #e4e6eb);
  padding: 2px 0 2px 12px;
  color: var(--text-dim, #6b7280);
  margin: 0.4em 0;
}

:deep(.ProseMirror pre) {
  background: #f6f8fa;
  padding: 12px 14px;
  border-radius: 6px;
  font-family: var(--mono);
  font-size: 13px;
  line-height: 1.55;
  overflow-x: auto;
}
:deep(.ProseMirror code) {
  background: rgba(0, 0, 0, .06);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 0.92em;
}
:deep(.ProseMirror pre code) {
  background: transparent;
  padding: 0;
  font-size: 13px;
}
:deep(.ProseMirror hr) {
  border: 0;
  border-top: 1px solid var(--border, #e4e6eb);
  margin: 1.4em 0;
}
:deep(.ProseMirror img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  display: block;
}
:deep(.ProseMirror a) {
  color: var(--accent, #6d28d9);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* Task list */
:deep(.ProseMirror ul[data-type="taskList"]) { list-style: none; padding-left: 0; }
:deep(.ProseMirror ul[data-type="taskList"] li) { display: flex; gap: 8px; align-items: flex-start; }
:deep(.ProseMirror ul[data-type="taskList"] li > label) { margin-top: 4px; user-select: none; }
:deep(.ProseMirror ul[data-type="taskList"] li > div) { flex: 1; }
:deep(.ProseMirror ul[data-type="taskList"] li[data-checked="true"] > div) {
  color: var(--text-dim, #6b7280); text-decoration: line-through;
}

/* Placeholder */
:deep(.ProseMirror p.is-editor-empty:first-child::before) {
  content: attr(data-placeholder);
  color: var(--text-dim, #9aa0a6);
  pointer-events: none;
  height: 0;
  float: left;
}

/* ─── drag handle pill ──────────────────────────────────────────────── */
.be-drag-handle-wrap {
  /* The wrapper element TipTap positions for us; the inner button is our
     visible affordance. Subtle by default, prominent on hover (matches
     Notion's "appears next to the hovered block" feel). */
  z-index: 5;
}
.be-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 22px;
  padding: 0;
  margin-right: 4px;
  border: 0;
  background: transparent;
  border-radius: 4px;
  color: var(--text-dim, #9aa0a6);
  cursor: grab;
  font-size: 11px;
  letter-spacing: -1px;
  line-height: 1;
  opacity: .65;
  transition: opacity .12s ease, background .12s ease;
}
.be-handle:hover { background: var(--accent-soft, #f3f4f6); opacity: 1; }
.be-handle:active { cursor: grabbing; }
</style>
