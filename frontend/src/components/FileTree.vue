<template>
  <ul class="tree" :class="{ root: depth === 0 }">
    <li v-for="node in nodes" :key="node.path">
      <template v-if="node.type === 'dir'">
        <div class="row item dir" :style="indent" @click="toggle(node.path)">
          <span class="caret" :class="{ open: isOpen(node.path) }">▸</span>
          <span class="icon">📁</span>
          <span class="label">{{ node.name }}</span>
        </div>
        <FileTree
          v-if="isOpen(node.path)"
          :nodes="node.children"
          :active-path="activePath"
          :depth="depth + 1"
          :open-set="openSet"
          @select="$emit('select', $event)"
          @toggle="$emit('toggle', $event)"
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
      </div>
    </li>
  </ul>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  activePath: { type: String, default: '' },
  depth: { type: Number, default: 0 },
  openSet: { type: Object, default: () => new Set() }
})
const emit = defineEmits(['select', 'toggle'])

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
.icon { font-size: 13px; }
.label { overflow: hidden; text-overflow: ellipsis; }
</style>
