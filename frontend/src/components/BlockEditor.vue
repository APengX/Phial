<template>
  <div class="block-editor-host">
    <EditorContent v-if="editor" :editor="editor" class="be-content" />
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
// PR 1 scope: prose-style HTML only. Docs that contain `<script>` are caught
// upstream in EditorView and never mounted into this component; the widget-
// block work in PR 3 will resolve that.

import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import Placeholder from '@tiptap/extension-placeholder'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

// Envelope = {prefix, suffix} where prefix ends right after `<body…>` open and
// suffix starts at `</body>`. Null means the input was a body fragment (no
// <body> tag at all) — we round-trip it raw.
let envelope = null
// Suppress onUpdate while we're applying an external value (file open / AI
// apply / first mount), so the same content doesn't bounce back to the parent.
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
    suffix: html.slice(closeIdx)
  }
}

function joinDoc(prefix, body, suffix) {
  if (!prefix && !suffix) return body
  return prefix + body + suffix
}

const editor = useEditor({
  extensions: [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] }
    }),
    Image.configure({ inline: false, allowBase64: true }),
    TaskList,
    TaskItem.configure({ nested: true }),
    Placeholder.configure({
      placeholder: () => t('blocks.placeholder')
    })
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
    }
  }
})

function applyExternal(html) {
  if (!editor.value) return
  const parts = splitDoc(html || '')
  envelope = (parts.prefix || parts.suffix) ? { prefix: parts.prefix, suffix: parts.suffix } : null
  suppressUpdate = true
  editor.value.commands.setContent(parts.body || '<p></p>', { emitUpdate: false })
  // Microtask gap to be safe — some TipTap versions schedule the update.
  queueMicrotask(() => { suppressUpdate = false })
}

onMounted(() => applyExternal(props.modelValue))

watch(
  () => props.modelValue,
  (val) => {
    if (!editor.value) return
    const parts = splitDoc(val || '')
    const currentBody = editor.value.getHTML()
    const sameBody = parts.body === currentBody
    const samePrefix = (envelope?.prefix || '') === (parts.prefix || '')
    const sameSuffix = (envelope?.suffix || '') === (parts.suffix || '')
    if (sameBody && samePrefix && sameSuffix) return
    applyExternal(val)
  }
)

onBeforeUnmount(() => editor.value?.destroy())

defineExpose({
  focus: () => editor.value?.commands.focus()
})
</script>

<style scoped>
.block-editor-host {
  height: 100%;
  overflow: auto;
  background: var(--bg, #fff);
}
.be-content {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 40px 80px;
}

/* ProseMirror surface — typography tuned to feel like reading a doc, not a
   form. Selection / focus stays minimal because Phial already has the topbar
   for actions. */
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

/* Task lists — StarterKit gives us bullet/ordered; TaskList is opt-in. */
:deep(.ProseMirror ul[data-type="taskList"]) {
  list-style: none;
  padding-left: 0;
}
:deep(.ProseMirror ul[data-type="taskList"] li) {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
:deep(.ProseMirror ul[data-type="taskList"] li > label) {
  margin-top: 4px;
  user-select: none;
}
:deep(.ProseMirror ul[data-type="taskList"] li > div) { flex: 1; }
:deep(.ProseMirror ul[data-type="taskList"] li[data-checked="true"] > div) {
  color: var(--text-dim, #6b7280);
  text-decoration: line-through;
}

/* Placeholder text on the first empty paragraph. */
:deep(.ProseMirror p.is-editor-empty:first-child::before) {
  content: attr(data-placeholder);
  color: var(--text-dim, #9aa0a6);
  pointer-events: none;
  height: 0;
  float: left;
}
</style>
