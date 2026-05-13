<template>
  <NodeViewWrapper as="details" class="phial-toggle" :open="true">
    <!-- Chevron lives outside the ProseMirror content (it isn't part of the
         node's children), positioned absolutely over the summary area. The
         <details> renders open=true always while editing — what the chevron
         flips is the SAVED `open` attr, i.e. what readers see first. -->
    <button
      type="button"
      class="tg-chev"
      :class="{ closed: !node.attrs.open }"
      :title="node.attrs.open ? t('blocks.toggle.savedOpen') : t('blocks.toggle.savedClosed')"
      :contenteditable="false"
      @mousedown.prevent
      @click="toggleSaved"
    >▾</button>

    <!-- NodeViewContent gets the toggleSummary + block+ children at the
         right slots — the first child renders into <summary>, the rest sit
         as ordinary <details> body content. -->
    <NodeViewContent />
  </NodeViewWrapper>
</template>

<script setup>
// NodeView for the Toggle (`<details>`) block. The block's schema content
// is `toggleSummary block+`; we don't touch that — the chevron is pure
// chrome (contenteditable=false, no ProseMirror position), and it writes
// to the parent's `open` node attribute. RenderHTML on the Toggle node
// emits `open` only when this attr is true, so the saved doc captures the
// reader-facing default while the editor always shows the body.
import { NodeViewWrapper, NodeViewContent, nodeViewProps } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'

const props = defineProps(nodeViewProps)
const { t } = useI18n()

function toggleSaved() {
  props.updateAttributes({ open: !props.node.attrs.open })
}
</script>

<style scoped>
.phial-toggle {
  position: relative;
  border-left: 2px solid var(--border, #e4e6eb);
  padding: 4px 0 4px 22px;
  margin: 0.4em 0;
}
.phial-toggle :deep(> summary) {
  cursor: text;
  font-weight: 500;
  list-style: none;
  outline: none;
}
.phial-toggle :deep(> summary::-webkit-details-marker) { display: none; }
.phial-toggle :deep(> summary + *) { margin-top: 4px; }

.tg-chev {
  position: absolute;
  left: 4px;
  top: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 10px;
  color: var(--text-dim, #6b7280);
  border-radius: 3px;
  cursor: pointer;
  transition: transform .12s ease, background .12s ease;
  z-index: 2;
}
.tg-chev:hover { background: var(--accent-soft, #f3f4f6); color: var(--accent, #6d28d9); }
.tg-chev.closed { transform: rotate(-90deg); }
</style>
