<template>
  <div class="graph-view">
    <header class="gv-top">
      <button class="ghost" @click="goBack">‹ {{ t('editor.back') }}</button>
      <strong class="gv-title">🕸 {{ t('nav.graph') }}</strong>
      <span class="gv-hint muted">{{ t('nav.graphHint') }}</span>
    </header>
    <div class="gv-body">
      <GraphCanvas @open="open" />
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphCanvas from '@/components/GraphCanvas.vue'

const router = useRouter()
const { t } = useI18n()

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push({ name: 'home' })
}
function open(path) {
  router.push({ name: 'editor', query: { path } })
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
.gv-body { flex: 1; min-height: 0; }
</style>
