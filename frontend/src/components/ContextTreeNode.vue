<template>
  <li class="node" :class="node.type">
    <div
      class="row"
      :class="{ on: rowChecked, partial: rowPartial }"
      :style="{ paddingLeft: 8 + depth * 16 + 'px' }"
    >
      <!-- chevron (dirs only) -->
      <button
        v-if="node.type === 'dir'"
        class="caret"
        :class="{ open }"
        :title="open ? '' : ''"
        @click="$emit('toggle-open', node.path)"
      >▸</button>
      <span v-else class="caret-spacer" aria-hidden="true"></span>

      <!-- checkbox -->
      <input
        type="checkbox"
        v-indeterminate="node.type === 'dir' && rowPartial"
        :checked="rowChecked"
        @change="onCheck($event.target.checked)"
      />

      <!-- name + (file size) -->
      <span class="icon" aria-hidden="true">{{ fileIcon }}</span>
      <span class="name" @click="onLabelClick">{{ node.name }}</span>
      <span v-if="node.type === 'file' && node.kind === 'attach'" class="kind-tag" title="作为附件原生发送给模型">PDF</span>
      <span v-if="node.type === 'file'" class="size muted">{{ fmtBytes(node.size) }}</span>
      <span v-else-if="node.allFiles.length" class="count muted">
        {{ pickedUnder }}/{{ node.allFiles.length }}
      </span>
    </div>

    <!-- recurse into directory children -->
    <ul v-if="node.type === 'dir' && open && node.children.length" class="children">
      <ContextTreeNode
        v-for="child in node.children"
        :key="child.path || child.rel"
        :node="child"
        :picks="picks"
        :open-set="openSet"
        :depth="depth + 1"
        @toggle-file="$emit('toggle-file', $event)"
        @toggle-dir="$emit('toggle-dir', $event)"
        @toggle-open="$emit('toggle-open', $event)"
      />
    </ul>
  </li>
</template>

<script setup>
// One node of the directory tree inside a bound context folder.
// Recursive: when `node.type === 'dir'` and it's open, renders ContextTreeNode
// for each child. State (picks, open set) is hoisted to the picker so toggles
// can persist and tri-state checkboxes stay consistent across siblings.

import { computed } from 'vue'

const props = defineProps({
  // node:
  //   { type:'file', name, rel, size }
  //   { type:'dir',  name, path, children:[...], allFiles:[<rel>, ...] }
  node: { type: Object, required: true },
  picks: { type: Object, required: true },     // reactive Set<rel>
  openSet: { type: Object, required: true },   // reactive Set<dirPath>
  depth: { type: Number, default: 0 }
})
const emit = defineEmits(['toggle-file', 'toggle-dir', 'toggle-open'])

// Reading `.size` on the Sets is what makes Vue track them — picks/openSet are
// reactive proxies, and any change to add/delete reruns these computeds.
const open = computed(() => props.openSet.has(props.node.path))

const fileIcon = computed(() => {
  if (props.node.type === 'dir') return '📁'
  return props.node.kind === 'attach' ? '📕' : '📄'
})

const pickedUnder = computed(() => {
  if (props.node.type !== 'dir') return 0
  let n = 0
  for (const r of props.node.allFiles) if (props.picks.has(r)) n++
  return n
})

const rowChecked = computed(() => {
  if (props.node.type === 'file') return props.picks.has(props.node.rel)
  const total = props.node.allFiles.length
  return total > 0 && pickedUnder.value === total
})

const rowPartial = computed(() => {
  if (props.node.type !== 'dir') return false
  const p = pickedUnder.value
  return p > 0 && p < props.node.allFiles.length
})

function onCheck(checked) {
  if (props.node.type === 'file') {
    emit('toggle-file', { rel: props.node.rel, on: checked })
  } else {
    emit('toggle-dir', { node: props.node, on: checked })
  }
}

// Clicking the name of a dir is a natural way to expand/collapse — matches the
// chevron without making the user aim at it.
function onLabelClick() {
  if (props.node.type === 'dir') emit('toggle-open', props.node.path)
}

function fmtBytes(b) {
  if (!b) return '0 B'
  if (b < 1024) return b + ' B'
  return (b / 1024).toFixed(b < 10 * 1024 ? 1 : 0) + ' KB'
}

// Tiny directive to drive the native `indeterminate` property (which can't be
// set declaratively in HTML — has to be assigned on the element). Defined in
// `<script setup>` with a `v…` const auto-registers as `v-indeterminate`.
const vIndeterminate = {
  mounted(el, binding) { el.indeterminate = !!binding.value },
  updated(el, binding) { el.indeterminate = !!binding.value }
}
</script>

<script>
// Need a `name` for the recursive `<ContextTreeNode>` reference inside template.
export default { name: 'ContextTreeNode' }
</script>

<style scoped>
.node { list-style: none; }
.children { list-style: none; margin: 0; padding: 0; }
.row {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 8px 3px 0; font-size: 12.5px; line-height: 1.45;
  border-radius: 5px; margin: 1px 4px;
}
.row:hover { background: var(--bg-soft); }
.row.on { background: var(--accent-soft); }
.row.partial { background: #f5f3ff; }

.caret {
  flex: none; width: 14px; padding: 0; border: 0; background: transparent;
  color: var(--text-dim); font-size: 10px; cursor: pointer; transition: transform 0.12s;
}
.caret.open { transform: rotate(90deg); }
.caret-spacer { display: inline-block; width: 14px; flex: none; }

input[type="checkbox"] { flex: none; margin: 0; cursor: pointer; }
.icon { font-size: 13px; flex: none; }
.name {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  cursor: pointer; user-select: none;
}
.size, .count { font-size: 11px; white-space: nowrap; flex: none; }
.kind-tag {
  font-size: 10px; padding: 0 5px; border-radius: 999px;
  background: rgba(199, 142, 63, 0.16); color: #8a6122; letter-spacing: 0.03em; flex: none;
}
</style>
