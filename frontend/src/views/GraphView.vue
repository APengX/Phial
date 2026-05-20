<template>
  <div class="graph-view">
    <header class="gv-top">
      <button class="ghost" @click="goBack">‹ {{ t('editor.back') }}</button>
      <strong class="gv-title">🕸 {{ t('nav.graph') }}</strong>
      <span class="gv-hint muted">{{ t('nav.graphHint') }}</span>
      <button
        class="ghost gv-link"
        @click="autoLinkOpen = true"
        :title="t('autolink.scanAllTip')"
      >
        🔗 {{ t('autolink.scanAllBtn') }}
      </button>
    </header>
    <div class="gv-body">
      <GraphCanvas :key="graphKey" @open="open" />
    </div>
    <AutoLinkAllModal v-model="autoLinkOpen" @applied="onApplied" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphCanvas from '@/components/GraphCanvas.vue'
import AutoLinkAllModal from '@/components/AutoLinkAllModal.vue'

const router = useRouter()
const { t } = useI18n()

const autoLinkOpen = ref(false)
const graphKey = ref(0)

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push({ name: 'home' })
}
function open(path) {
  router.push({ name: 'editor', query: { path } })
}
// links were written to disk — remount the canvas so new edges show up
function onApplied() {
  graphKey.value++
}
</script>

<style scoped>
.graph-view { display: flex; flex-direction: column; height: 100%; }
.gv-top {
  display: flex; align-items: baseline; gap: 12px;
  padding: 9px 14px; border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}
.gv-title { font-size: 15px; }
.gv-hint { font-size: 12px; }
.gv-link { margin-left: auto; align-self: center; }
.gv-body { flex: 1; min-height: 0; }
</style>
