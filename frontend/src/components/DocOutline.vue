<template>
  <div class="outline">
    <p v-if="!headings.length" class="ol-empty muted">{{ t('nav.outlineEmpty') }}</p>
    <ul v-else class="ol-list">
      <li
        v-for="h in headings"
        :key="h.index"
        class="ol-item"
        :class="'lvl-' + h.level"
        :title="h.text"
        @click="$emit('jump', h.index)"
      >
        <span class="ol-dot"></span>
        <span class="ol-text">{{ h.text }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  html: { type: String, default: '' }
})
defineEmits(['jump'])
const { t } = useI18n()

// Headings keep their *raw* enumeration index (including any empty ones we skip
// rendering) so it matches `document.querySelectorAll('h1,h2,h3')` inside the
// rendered iframe — that's how the preview scrolls to the right spot.
const headings = computed(() => {
  const out = []
  if (!props.html) return out
  try {
    const doc = new DOMParser().parseFromString(props.html, 'text/html')
    const hs = doc.querySelectorAll('h1,h2,h3')
    hs.forEach((el, i) => {
      const text = (el.textContent || '').replace(/\s+/g, ' ').trim()
      if (text) out.push({ index: i, level: Number(el.tagName[1]) || 1, text })
    })
  } catch {
    /* malformed HTML — show nothing */
  }
  return out
})
</script>

<style scoped>
.outline { padding: 6px 4px; }
.ol-empty { padding: 14px 10px; font-size: 12px; line-height: 1.6; }
.ol-list { list-style: none; margin: 0; padding: 0; }
.ol-item {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; margin: 1px 4px; border-radius: 5px;
  cursor: pointer; font-size: 12.5px; color: var(--text);
  white-space: nowrap; overflow: hidden;
}
.ol-item:hover { background: var(--bg-soft); }
.ol-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--text-dim); flex: none; opacity: 0.55;
}
.ol-text { overflow: hidden; text-overflow: ellipsis; }
.ol-item.lvl-1 { font-weight: 600; }
.ol-item.lvl-2 { padding-left: 20px; }
.ol-item.lvl-2 .ol-dot { width: 4px; height: 4px; }
.ol-item.lvl-3 { padding-left: 34px; color: var(--text-dim); }
.ol-item.lvl-3 .ol-dot { width: 3px; height: 3px; }
</style>
