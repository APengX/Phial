<template>
  <NodeViewWrapper as="aside" class="phial-callout" :data-icon="node.attrs.icon">
    <!-- Icon column. Click to pop the picker; emoji-only, no asset deps. -->
    <button
      type="button"
      class="co-icon"
      :title="t('blocks.callout.pickIcon')"
      :contenteditable="false"
      @mousedown.prevent
      @click="pickerOpen = !pickerOpen"
    >{{ node.attrs.icon }}</button>

    <div v-if="pickerOpen" class="co-picker" :contenteditable="false">
      <button
        v-for="ic in ICONS"
        :key="ic"
        type="button"
        class="co-picker-item"
        :class="{ active: ic === node.attrs.icon }"
        @mousedown.prevent="choose(ic)"
      >{{ ic }}</button>
    </div>

    <!-- Body — standard block content, edited like any other prose. -->
    <NodeViewContent class="co-body" />
  </NodeViewWrapper>
</template>

<script setup>
// NodeView for the Callout block. The body is plain block content (a
// NodeViewContent slot — ProseMirror writes the children into it). The icon
// is a node attribute managed by a small click-popover, marked
// `contenteditable=false` so ProseMirror leaves it alone.
import { ref } from 'vue'
import { NodeViewWrapper, NodeViewContent, nodeViewProps } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'

const props = defineProps(nodeViewProps)
const { t } = useI18n()

// Hand-picked, broadly available emoji. Avoids a third-party icon library
// and keeps the saved doc fully self-contained.
const ICONS = ['💡', '⚠️', '✅', '❌', '📝', 'ℹ️', '⭐', '🔥']

const pickerOpen = ref(false)
function choose(icon) {
  props.updateAttributes({ icon })
  pickerOpen.value = false
}
</script>

<style scoped>
.phial-callout {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: 10px;
  align-items: start;
  margin: 0.6em 0;
  padding: 12px 14px;
  background: #fff8e1;
  border: 1px solid #f1d56b;
  border-radius: 8px;
  position: relative;
}
.co-icon {
  width: 28px; height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  border-radius: 5px;
}
.co-icon:hover { background: rgba(0, 0, 0, .05); }
.co-body { min-width: 0; }
.co-body :deep(p:first-child) { margin-top: 2px; }
.co-body :deep(p:last-child)  { margin-bottom: 0; }

.co-picker {
  position: absolute;
  top: 38px;
  left: 8px;
  z-index: 50;
  display: flex;
  gap: 2px;
  padding: 4px;
  background: #fff;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 6px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, .12);
}
.co-picker-item {
  width: 28px; height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  border-radius: 5px;
}
.co-picker-item:hover { background: var(--accent-soft, #f3f4f6); }
.co-picker-item.active { background: var(--accent-soft, #ede9fe); outline: 1px solid var(--accent, #6d28d9); }
</style>
