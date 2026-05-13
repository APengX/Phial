<template>
  <ul class="tree" :class="{ root: depth === 0 }">
    <li v-for="node in nodes" :key="node.path">
      <template v-if="node.type === 'dir'">
        <div class="row item dir" :style="indent" @click="toggle(node.path)">
          <span class="caret" :class="{ open: isOpen(node.path) }">▸</span>
          <span class="icon">📁</span>
          <span class="label">{{ node.name }}</span>
          <span class="acts">
            <button class="t-act danger" :title="t('editor.delete')" @click.stop="$emit('delete', node)">🗑</button>
          </span>
        </div>
        <FileTree
          v-if="isOpen(node.path)"
          :nodes="node.children"
          :active-path="activePath"
          :depth="depth + 1"
          :open-set="openSet"
          @select="$emit('select', $event)"
          @toggle="$emit('toggle', $event)"
          @delete="$emit('delete', $event)"
          @rename="$emit('rename', $event)"
        />
      </template>
      <div
        v-else
        class="row item doc"
        :class="{ active: node.path === activePath }"
        :style="indent"
        @click="$emit('select', node.path)"
        :title="node.title || node.name"
      >
        <span class="icon">📄</span>
        <span class="label">{{ node.title || node.name }}</span>
        <span class="acts">
          <button class="t-act" :title="t('editor.rename')" @click.stop="$emit('rename', node)">✎</button>
          <button class="t-act danger" :title="t('editor.delete')" @click.stop="$emit('delete', node)">🗑</button>
        </span>
      </div>
    </li>
  </ul>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  activePath: { type: String, default: '' },
  depth: { type: Number, default: 0 },
  openSet: { type: Object, default: () => new Set() }
})
const emit = defineEmits(['select', 'toggle', 'delete', 'rename'])
const { t } = useI18n()

const indent = computed(() => ({ paddingLeft: `${8 + props.depth * 14}px` }))
const isOpen = (p) => props.openSet.has(p)
function toggle(p) {
  emit('toggle', p)
}
</script>

<style scoped>
.tree { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.tree.root { padding: 4px 0; }
.item {
  padding: 4px 8px 4px 0;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
  border-radius: 5px;
  margin: 1px 4px;
  gap: 5px;
}
.item:hover { background: var(--bg-soft); }
.item.active { background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.caret {
  display: inline-block;
  width: 12px;
  transition: transform 0.12s;
  color: var(--text-dim);
  font-size: 10px;
}
.caret.open { transform: rotate(90deg); }
.icon { font-size: 13px; flex: none; }
.label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.acts { margin-left: auto; display: flex; gap: 2px; flex: none; opacity: 0; }
.item:hover .acts { opacity: 1; }
.t-act {
  border: 0; background: transparent; padding: 1px 4px; font-size: 11.5px; line-height: 1;
  border-radius: 4px; color: var(--text-dim);
}
.t-act:hover { background: var(--bg-panel); color: var(--text); }
.t-act.danger:hover { background: #fef2f2; color: var(--danger); }
</style>
