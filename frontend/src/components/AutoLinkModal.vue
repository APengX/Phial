<!-- Auto-link modal: scans the open document for mentions of other workspace
     documents and lets the user confirm which to turn into links. -->
<template>
  <div v-if="modelValue" class="modal-overlay" @click.self="close">
    <div class="autolink-modal">
      <header class="al-head">
        <h3>🔗 {{ t('autolink.title') }}</h3>
        <button class="ghost icon-btn" @click="close">✕</button>
      </header>
      <p class="al-intro">{{ t('autolink.intro') }}</p>

      <div class="al-body scroll">
        <div v-if="loading" class="al-state muted">{{ t('autolink.scanning') }}</div>
        <div v-else-if="error" class="al-state danger">{{ error }}</div>
        <div v-else-if="!candidates.length" class="al-state muted">
          {{ t('autolink.empty') }}
        </div>

        <template v-else>
          <div class="al-bar">
            <label class="al-selall">
              <input
                type="checkbox"
                :checked="allChecked"
                :indeterminate.prop="someChecked && !allChecked"
                @change="toggleAll"
              />
              {{ t('autolink.selectAll') }}
            </label>
            <span class="muted">{{ t('autolink.selected', { n: selectedCount, total: candidates.length }) }}</span>
          </div>

          <ul class="al-list">
            <li v-for="c in candidates" :key="c.id" class="al-row" @click="toggle(c.id)">
              <input type="checkbox" :checked="picked.has(c.id)" @click.stop="toggle(c.id)" />
              <div class="al-main">
                <div class="al-pair">
                  <span class="al-phrase">{{ c.phrase }}</span>
                  <span class="al-arrow">→</span>
                  <span class="al-target">{{ c.title }}</span>
                  <span class="pill" :class="c.kind === 'exact' ? 'olive' : 'clay'">
                    {{ c.kind === 'exact' ? t('autolink.exact') : t('autolink.ai') }}
                  </span>
                </div>
                <div v-if="c.snippet" class="al-snippet muted">{{ c.snippet }}</div>
              </div>
            </li>
          </ul>
        </template>
      </div>

      <footer class="al-foot">
        <button class="ghost" @click="close">{{ t('common.cancel') }}</button>
        <button
          class="primary"
          :disabled="!selectedCount || applying"
          @click="apply"
        >
          {{ applying ? t('autolink.applying') : t('autolink.apply') }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { autoLinkScan, autoLinkApply } from '@/api/documents'
import { pushToast } from '@/composables/useToast'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  path: { type: String, default: '' },
  html: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'applied'])
const { t } = useI18n()

const loading = ref(false)
const applying = ref(false)
const error = ref('')
const candidates = ref([])
const picked = ref(new Set())

const selectedCount = computed(() => picked.value.size)
const allChecked = computed(
  () => candidates.value.length > 0 && picked.value.size === candidates.value.length
)
const someChecked = computed(() => picked.value.size > 0)

function close() {
  emit('update:modelValue', false)
}

function toggle(id) {
  const next = new Set(picked.value)
  next.has(id) ? next.delete(id) : next.add(id)
  picked.value = next
}

function toggleAll() {
  picked.value = allChecked.value
    ? new Set()
    : new Set(candidates.value.map((c) => c.id))
}

async function scan() {
  loading.value = true
  error.value = ''
  candidates.value = []
  picked.value = new Set()
  try {
    const res = await autoLinkScan(props.path, props.html)
    candidates.value = res.candidates || []
    // pre-select everything — confirming is the common case
    picked.value = new Set(candidates.value.map((c) => c.id))
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

async function apply() {
  if (!selectedCount.value || applying.value) return
  applying.value = true
  try {
    const picks = candidates.value
      .filter((c) => picked.value.has(c.id))
      .map((c) => ({ phrase: c.phrase, target: c.target }))
    const res = await autoLinkApply(props.path, props.html, picks)
    emit('applied', res.html)
    pushToast(t('autolink.applied', { n: res.applied }), 'success', 2000)
    close()
  } catch (e) {
    pushToast(e.message || String(e), 'error')
  } finally {
    applying.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) scan()
  }
)
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 20, 19, 0.34);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 90;
}
.autolink-modal {
  width: 540px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 96px);
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.al-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 0;
}
.al-head h3 {
  margin: 0;
  font-size: 17px;
}
.al-intro {
  margin: 6px 18px 12px;
  font-size: 12.5px;
  color: var(--text-dim);
  line-height: 1.55;
}
.al-body {
  flex: 1;
  min-height: 96px;
  overflow-y: auto;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.al-state {
  padding: 32px 18px;
  text-align: center;
  font-size: 13px;
}
.al-state.danger {
  color: var(--danger);
}
.al-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 18px;
  font-size: 12px;
  background: var(--bg-soft);
  position: sticky;
  top: 0;
}
.al-selall {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-weight: 500;
}
.al-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
}
.al-row {
  display: flex;
  gap: 10px;
  padding: 9px 18px;
  cursor: pointer;
  align-items: flex-start;
}
.al-row:hover {
  background: var(--bg-soft);
}
.al-row > input {
  margin-top: 2px;
}
.al-main {
  flex: 1;
  min-width: 0;
}
.al-pair {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.al-phrase {
  font-weight: 600;
  color: var(--accent-strong);
}
.al-arrow {
  color: var(--text-mute);
}
.al-target {
  color: var(--text);
}
.al-snippet {
  margin-top: 3px;
  font-size: 11.5px;
  line-height: 1.5;
}
.al-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
}
.icon-btn {
  padding: 4px 8px;
}
</style>
