<template>
  <div v-if="open" class="we-overlay" @click.self="cancel">
    <div class="we-modal" role="dialog" aria-modal="true">
      <header class="we-head">
        <strong>{{ t('blocks.widget.editTitle') }}</strong>
        <button class="ghost x" :title="t('blocks.widget.cancel')" @click="cancel">×</button>
      </header>

      <p class="we-intro muted">{{ t('blocks.widget.editIntro') }}</p>

      <div class="we-editor">
        <!-- Reuse the existing CodeMirror+HTML-mode editor used for the
             whole-doc source view — same keybindings (Cmd+S submits Apply
             here), same syntax highlight, no parallel codebase to maintain. -->
        <HtmlEditor v-model="draftHtml" @save="apply" />
      </div>

      <footer class="we-foot">
        <span class="muted small">{{ t('blocks.widget.editHint') }}</span>
        <span class="we-spacer"></span>
        <button class="ghost" @click="cancel">{{ t('blocks.widget.cancel') }}</button>
        <button class="primary" @click="apply">{{ t('blocks.widget.apply') }}</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
// Modal for editing one widget's raw HTML. The host (BlockEditor.vue) opens
// it with an initial HTML string + an `update(html)` callback that writes
// the new HTML back to the specific TipTap node. We don't hold a reference
// to the node ourselves — keeping the modal node-unaware avoids stale-ref
// issues if the user deletes the block while the modal is open.

import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import HtmlEditor from '@/components/HtmlEditor.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  initialHtml: { type: String, default: '' },
})
const emit = defineEmits(['apply', 'cancel'])
const { t } = useI18n()

const draftHtml = ref('')

watch(
  () => [props.open, props.initialHtml],
  ([isOpen, html]) => {
    if (isOpen) draftHtml.value = html || ''
  },
  { immediate: true }
)

function apply() {
  emit('apply', draftHtml.value)
}
function cancel() {
  emit('cancel')
}
</script>

<style scoped>
.we-overlay {
  position: fixed; inset: 0;
  background: rgba(15, 18, 25, .42);
  display: flex; align-items: center; justify-content: center;
  z-index: 1200;
  padding: 20px;
}
.we-modal {
  width: min(840px, 100%);
  max-height: min(80vh, 720px);
  display: flex; flex-direction: column;
  background: #fff;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0,0,0,.18);
  overflow: hidden;
}
.we-head {
  display: flex; align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border, #e4e6eb);
}
.we-head strong { flex: 1; font-size: 14px; }
.we-head .x { padding: 2px 9px; font-size: 16px; }

.we-intro {
  padding: 10px 14px 6px;
  font-size: 12.5px;
  line-height: 1.5;
  margin: 0;
}

.we-editor { flex: 1; min-height: 280px; border-top: 1px solid var(--border, #e4e6eb); }
.we-editor :deep(.cm-host) { height: 100%; min-height: 280px; }

.we-foot {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border, #e4e6eb);
  background: var(--bg-panel, #fafbfc);
}
.we-foot .small { font-size: 12px; }
.we-spacer { flex: 1; }
</style>
