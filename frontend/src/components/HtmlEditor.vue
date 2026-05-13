<template>
  <div ref="host" class="cm-host"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'
import { keymap } from '@codemirror/view'
import { html as htmlLang } from '@codemirror/lang-html'

const props = defineProps({
  modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'save'])

const host = ref(null)
let view = null

onMounted(() => {
  const updateListener = EditorView.updateListener.of((v) => {
    if (v.docChanged) emit('update:modelValue', v.state.doc.toString())
  })
  const saveKey = keymap.of([
    {
      key: 'Mod-s',
      preventDefault: true,
      run: () => {
        emit('save')
        return true
      }
    }
  ])
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        htmlLang(),
        saveKey,
        updateListener,
        EditorView.lineWrapping,
        EditorView.theme({
          '&': { height: '100%', fontSize: '13px' },
          '.cm-scroller': { fontFamily: 'var(--mono)' }
        })
      ]
    })
  })
})

onBeforeUnmount(() => view?.destroy())

// External changes (open another doc, AI applied a result) -> replace contents.
watch(
  () => props.modelValue,
  (val) => {
    if (!view) return
    const cur = view.state.doc.toString()
    if (val !== cur) {
      view.dispatch({ changes: { from: 0, to: cur.length, insert: val ?? '' } })
    }
  }
)

defineExpose({ focus: () => view?.focus() })
</script>

<style scoped>
.cm-host {
  height: 100%;
  overflow: hidden;
}
:deep(.cm-editor) { height: 100%; }
:deep(.cm-editor.cm-focused) { outline: none; }
</style>
