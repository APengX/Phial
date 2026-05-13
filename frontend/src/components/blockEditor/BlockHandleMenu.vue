<template>
  <div
    v-if="open"
    ref="rootEl"
    class="blk-menu"
    :style="{ top: top + 'px', left: left + 'px' }"
    @click.stop
  >
    <!-- Turn into is only meaningful for "simple" blocks where one node type
         can sensibly replace another. For widgets / tables / columns /
         toggles, the conversion would lose structure (and TipTap's
         set/toggle commands no-op on them anyway), so the section is
         hidden — keeps the menu tidy and avoids surprising the user. -->
    <div
      v-if="turnIntoApplicable"
      class="blk-row has-sub"
      @mouseenter="subOpen = true"
      @mouseleave="subOpen = false"
    >
      <span class="ic" aria-hidden="true">↺</span>
      <span class="t">{{ t('blocks.menu.turnInto') }}</span>
      <span class="chev" aria-hidden="true">▸</span>

      <div v-if="subOpen" class="blk-sub">
        <button
          v-for="opt in turnIntoOptions"
          :key="opt.key"
          type="button"
          class="blk-row"
          @click.stop="onTurnInto(opt)"
        >
          <span class="ic" aria-hidden="true">{{ opt.icon }}</span>
          <span class="t">{{ opt.title }}</span>
        </button>
      </div>
    </div>

    <button type="button" class="blk-row" @click="emit('duplicate')">
      <span class="ic" aria-hidden="true">⎘</span>
      <span class="t">{{ t('blocks.menu.duplicate') }}</span>
    </button>

    <div class="blk-divider"></div>

    <button type="button" class="blk-row danger" @click="emit('delete')">
      <span class="ic" aria-hidden="true">✕</span>
      <span class="t">{{ t('blocks.menu.delete') }}</span>
    </button>
  </div>
</template>

<script setup>
// Floating "block menu" anchored next to the drag handle. Notion shows this
// when you click the ⋮⋮ handle: Turn into ▸ / Duplicate / Delete. The
// menu is purely a UI emitter — the editor commands run in BlockEditor.vue
// where we have the editor instance and the currently-hovered node + pos.
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  open: { type: Boolean, default: false },
  top: { type: Number, default: 0 },
  left: { type: Number, default: 0 },
  // Node type name of the block under the handle (TipTap node name, e.g.
  // 'paragraph', 'heading', 'table', 'phialWidget'). Drives whether the
  // Turn-into submenu shows up.
  nodeType: { type: String, default: '' },
})
const emit = defineEmits(['turnInto', 'duplicate', 'delete', 'close'])
const { t } = useI18n()

const rootEl = ref(null)
const subOpen = ref(false)

// Turn-into makes sense for "simple" prose-shaped blocks. For composite or
// special-purpose blocks (widget HTML, table, columns, toggle), the
// conversion would either no-op or drop structure — hide it.
const TURN_INTO_OK = new Set([
  'paragraph', 'heading', 'blockquote', 'codeBlock',
  'bulletList', 'orderedList', 'taskList',
  'callout',
])
const turnIntoApplicable = computed(() => TURN_INTO_OK.has(props.nodeType))

// Match the slash menu's block list — same icons, same set. Centralizing
// these in a shared file is overkill for two consumers; we'll lift it if a
// third caller appears.
const turnIntoOptions = [
  { key: 'paragraph', icon: '¶',  title: t('blocks.items.paragraph') },
  { key: 'h1',        icon: 'H₁', title: t('blocks.items.h1') },
  { key: 'h2',        icon: 'H₂', title: t('blocks.items.h2') },
  { key: 'h3',        icon: 'H₃', title: t('blocks.items.h3') },
  { key: 'ul',        icon: '•',  title: t('blocks.items.ul') },
  { key: 'ol',        icon: '1.', title: t('blocks.items.ol') },
  { key: 'task',      icon: '☐',  title: t('blocks.items.task') },
  { key: 'quote',     icon: '❝',  title: t('blocks.items.quote') },
  { key: 'code',      icon: '⌨',  title: t('blocks.items.code') },
]

function onTurnInto(opt) {
  emit('turnInto', opt.key)
}
</script>

<style scoped>
.blk-menu {
  position: fixed;
  z-index: 1001;
  min-width: 180px;
  background: #fff;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .12);
  padding: 4px;
  font-size: 13px;
}

.blk-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  background: transparent;
  border-radius: 5px;
  cursor: pointer;
  text-align: left;
  color: inherit;
  position: relative;
}
.blk-row:hover { background: var(--accent-soft, #f3f4f6); }
.blk-row.has-sub { padding-right: 16px; }
.blk-row.danger { color: #b91c1c; }
.blk-row.danger:hover { background: #fee2e2; }
.blk-row .ic {
  width: 18px;
  text-align: center;
  font-size: 13px;
  color: var(--text-dim, #6b7280);
}
.blk-row.danger .ic { color: #b91c1c; }
.blk-row .t { flex: 1; }
.blk-row .chev { font-size: 10px; color: var(--text-dim, #6b7280); }

.blk-sub {
  position: absolute;
  top: -4px;
  left: 100%;
  margin-left: 2px;
  min-width: 180px;
  background: #fff;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .12);
  padding: 4px;
}

.blk-divider {
  height: 1px;
  background: var(--border, #e4e6eb);
  margin: 4px 2px;
}
</style>
