<template>
  <div
    v-if="items.length || query"
    ref="rootEl"
    class="slash-menu"
    :style="{ top: top + 'px', left: left + 'px' }"
    role="listbox"
  >
    <div v-if="!items.length" class="slash-empty muted">
      {{ t('blocks.slashEmpty', { q: query }) }}
    </div>
    <button
      v-for="(item, i) in items"
      :key="item.key"
      ref="itemEls"
      type="button"
      class="slash-item"
      :class="{ active: i === activeIndex }"
      role="option"
      :aria-selected="i === activeIndex"
      @mousedown.prevent="$emit('pick', i)"
      @mouseenter="$emit('hover', i)"
    >
      <span class="ic" aria-hidden="true">{{ item.icon }}</span>
      <span class="lbl">
        <span class="t">{{ item.title }}</span>
        <span v-if="item.hint" class="h">{{ item.hint }}</span>
      </span>
    </button>
  </div>
</template>

<script setup>
// Floating menu that the slashCommands extension drives via render hooks.
// Stateless: parent owns `items`, `activeIndex`, `query`, position — this
// component just paints them and emits pick/hover. Arrow-key navigation
// lives in the parent (it has access to the editor) so this stays dumb.
import { ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  items: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: 0 },
  top: { type: Number, default: 0 },
  left: { type: Number, default: 0 },
  query: { type: String, default: '' },
})
defineEmits(['pick', 'hover'])

const { t } = useI18n()
const rootEl = ref(null)
const itemEls = ref([])

// Keep the active row scrolled into view as the user arrow-keys through.
watch(
  () => props.activeIndex,
  async (i) => {
    await nextTick()
    const el = itemEls.value?.[i]
    if (el && rootEl.value) {
      const er = el.getBoundingClientRect()
      const rr = rootEl.value.getBoundingClientRect()
      if (er.top < rr.top) el.scrollIntoView({ block: 'nearest' })
      else if (er.bottom > rr.bottom) el.scrollIntoView({ block: 'nearest' })
    }
  }
)
</script>

<style scoped>
.slash-menu {
  position: fixed;
  z-index: 1000;
  min-width: 260px;
  max-width: 320px;
  max-height: 320px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .12);
  padding: 4px;
  font-size: 13px;
}
.slash-empty { padding: 10px 12px; font-size: 12.5px; }
.slash-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  background: transparent;
  border-radius: 5px;
  cursor: pointer;
  text-align: left;
  color: inherit;
}
.slash-item.active, .slash-item:hover {
  background: var(--accent-soft, #f3f4f6);
}
.slash-item .ic {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: 14px;
  background: var(--bg-soft, #f8f8f9);
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 5px;
  flex: 0 0 26px;
}
.slash-item .lbl { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.slash-item .lbl .t { font-size: 13.5px; line-height: 1.25; }
.slash-item .lbl .h {
  font-size: 11.5px;
  color: var(--text-dim, #6b7280);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
