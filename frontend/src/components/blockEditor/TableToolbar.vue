<template>
  <div
    v-if="open"
    class="tt"
    :style="{ top: top + 'px', left: left + 'px' }"
    :contenteditable="false"
    @mousedown.stop
  >
    <button type="button" class="tt-btn" :title="t('blocks.table.rowAbove')" @click="run('addRowBefore')">↑+</button>
    <button type="button" class="tt-btn" :title="t('blocks.table.rowBelow')" @click="run('addRowAfter')">↓+</button>
    <span class="tt-sep"></span>
    <button type="button" class="tt-btn" :title="t('blocks.table.colLeft')"  @click="run('addColumnBefore')">←+</button>
    <button type="button" class="tt-btn" :title="t('blocks.table.colRight')" @click="run('addColumnAfter')">+→</button>
    <span class="tt-sep"></span>
    <button type="button" class="tt-btn danger" :title="t('blocks.table.delRow')" @click="run('deleteRow')">−↕</button>
    <button type="button" class="tt-btn danger" :title="t('blocks.table.delCol')" @click="run('deleteColumn')">−↔</button>
    <span class="tt-sep"></span>
    <button type="button" class="tt-btn danger" :title="t('blocks.table.delTable')" @click="run('deleteTable')">✕</button>
  </div>
</template>

<script setup>
// Floating mini-toolbar that the host (BlockEditor.vue) positions over a
// focused table. The toolbar itself is stateless — the host decides when
// to show it (cursor inside a table) and where (table's bounding box).
// Each button runs one of TipTap's built-in table commands.
import { useI18n } from 'vue-i18n'

const props = defineProps({
  open: { type: Boolean, default: false },
  top: { type: Number, default: 0 },
  left: { type: Number, default: 0 },
  // Pass the editor so commands run against the current cursor position
  // (the table commands operate relative to where the cursor is).
  editor: { type: Object, default: null },
})
const { t } = useI18n()

function run(cmd) {
  const ed = props.editor
  if (!ed) return
  // Chain via focus() so the cursor sticks inside the table (otherwise
  // clicking a toolbar button moves focus away and the next click would
  // fail with "no cell selected").
  ed.chain().focus()[cmd]?.().run()
}
</script>

<style scoped>
.tt {
  position: fixed;
  z-index: 900;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px 4px;
  background: #fff;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 6px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, .1);
  font-size: 12px;
}
.tt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 22px;
  min-width: 26px;
  padding: 0 5px;
  border: 0;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text, #1f2328);
  letter-spacing: -.5px;
}
.tt-btn:hover { background: var(--accent-soft, #f3f4f6); }
.tt-btn.danger { color: var(--danger); }
.tt-btn.danger:hover { background: #f7eae8; }
.tt-sep {
  width: 1px;
  height: 14px;
  background: var(--border, #e4e6eb);
  margin: 0 2px;
}
</style>
