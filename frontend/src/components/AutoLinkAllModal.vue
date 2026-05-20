<!-- Workspace-wide auto-link: scans every document for exact mentions of other
     documents, grouped by source doc, and applies the confirmed links to disk. -->
<template>
  <div v-if="modelValue" class="modal-overlay" @click.self="close">
    <div class="ala-modal">
      <header class="ala-head">
        <h3>🔗 {{ t('autolink.title') }}</h3>
        <button class="ghost icon-btn" @click="close">✕</button>
      </header>
      <p class="ala-intro">{{ t('autolink.scanAllIntro') }}</p>

      <div class="ala-body scroll">
        <div v-if="loading" class="ala-state muted">{{ t('autolink.scanning') }}</div>
        <div v-else-if="error" class="ala-state danger">{{ error }}</div>
        <div v-else-if="!totalCount" class="ala-state muted">{{ t('autolink.empty') }}</div>

        <template v-else>
          <div class="ala-bar">
            <label class="ala-selall">
              <input
                type="checkbox"
                :checked="allChecked"
                :indeterminate.prop="someChecked && !allChecked"
                @change="toggleAll"
              />
              {{ t('autolink.selectAll') }}
            </label>
            <span class="muted">{{ t('autolink.selected', { n: picked.size, total: totalCount }) }}</span>
          </div>

          <section v-for="g in groups" :key="g.path" class="ala-group">
            <label class="ala-ghead">
              <input
                type="checkbox"
                :checked="groupChecked(g)"
                :indeterminate.prop="groupSome(g) && !groupChecked(g)"
                @change="toggleGroup(g)"
              />
              <span class="ala-gtitle">{{ g.title }}</span>
              <code class="muted ala-gpath">{{ g.path }}</code>
            </label>
            <ul class="ala-list">
              <li
                v-for="c in g.candidates"
                :key="c.id"
                class="ala-row"
                @click="toggle(keyOf(g.path, c.id))"
              >
                <input
                  type="checkbox"
                  :checked="picked.has(keyOf(g.path, c.id))"
                  @click.stop="toggle(keyOf(g.path, c.id))"
                />
                <div class="ala-main">
                  <div class="ala-pair">
                    <span class="ala-phrase">{{ c.phrase }}</span>
                    <span class="ala-arrow">→</span>
                    <span class="ala-target">{{ c.title }}</span>
                  </div>
                  <div v-if="c.snippet" class="ala-snippet muted">{{ c.snippet }}</div>
                </div>
              </li>
            </ul>
          </section>
        </template>
      </div>

      <footer class="ala-foot">
        <button class="ghost" @click="close">{{ t('common.cancel') }}</button>
        <button class="primary" :disabled="!picked.size || applying" @click="apply">
          {{ applying ? t('autolink.applying') : t('autolink.apply') }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { autoLinkScanAll, autoLinkApplyAll } from '@/api/documents'
import { pushToast } from '@/composables/useToast'

const props = defineProps({
  modelValue: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'applied'])
const { t } = useI18n()

const loading = ref(false)
const applying = ref(false)
const error = ref('')
const groups = ref([])
const picked = ref(new Set())

// a candidate is keyed by its source doc + id (ids are per-group)
const keyOf = (path, id) => path + '::' + id
const allKeys = computed(() =>
  groups.value.flatMap((g) => g.candidates.map((c) => keyOf(g.path, c.id)))
)
const totalCount = computed(() => allKeys.value.length)
const allChecked = computed(
  () => totalCount.value > 0 && picked.value.size === totalCount.value
)
const someChecked = computed(() => picked.value.size > 0)

function close() {
  emit('update:modelValue', false)
}

function toggle(key) {
  const next = new Set(picked.value)
  next.has(key) ? next.delete(key) : next.add(key)
  picked.value = next
}

function toggleAll() {
  picked.value = allChecked.value ? new Set() : new Set(allKeys.value)
}

const groupKeys = (g) => g.candidates.map((c) => keyOf(g.path, c.id))
const groupChecked = (g) => g.candidates.length > 0 && groupKeys(g).every((k) => picked.value.has(k))
const groupSome = (g) => groupKeys(g).some((k) => picked.value.has(k))

function toggleGroup(g) {
  const next = new Set(picked.value)
  const on = groupChecked(g)
  for (const k of groupKeys(g)) on ? next.delete(k) : next.add(k)
  picked.value = next
}

async function scan() {
  loading.value = true
  error.value = ''
  groups.value = []
  picked.value = new Set()
  try {
    const res = await autoLinkScanAll()
    groups.value = res.groups || []
    picked.value = new Set(allKeys.value) // pre-select everything
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

async function apply() {
  if (!picked.value.size || applying.value) return
  applying.value = true
  try {
    const payload = groups.value
      .map((g) => ({
        path: g.path,
        picks: g.candidates
          .filter((c) => picked.value.has(keyOf(g.path, c.id)))
          .map((c) => ({ phrase: c.phrase, target: c.target }))
      }))
      .filter((g) => g.picks.length)
    const res = await autoLinkApplyAll(payload)
    pushToast(t('autolink.appliedAll', { n: res.applied, docs: res.docs }), 'success', 2600)
    emit('applied')
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
.ala-modal {
  width: 600px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 80px);
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.ala-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 0;
}
.ala-head h3 {
  margin: 0;
  font-size: 17px;
}
.ala-intro {
  margin: 6px 18px 12px;
  font-size: 12.5px;
  color: var(--text-dim);
  line-height: 1.55;
}
.ala-body {
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.ala-state {
  padding: 36px 18px;
  text-align: center;
  font-size: 13px;
}
.ala-state.danger {
  color: var(--danger);
}
.ala-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 18px;
  font-size: 12px;
  background: var(--bg-soft);
  position: sticky;
  top: 0;
  z-index: 1;
}
.ala-selall {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-weight: 500;
}
.ala-group {
  border-bottom: 1px solid var(--border);
}
.ala-group:last-child {
  border-bottom: none;
}
.ala-ghead {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 18px 4px;
  cursor: pointer;
}
.ala-gtitle {
  font-family: var(--serif);
  font-weight: 500;
  font-size: 14px;
}
.ala-gpath {
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ala-list {
  list-style: none;
  margin: 0;
  padding: 2px 0 8px;
}
.ala-row {
  display: flex;
  gap: 10px;
  padding: 6px 18px 6px 30px;
  cursor: pointer;
  align-items: flex-start;
}
.ala-row:hover {
  background: var(--bg-soft);
}
.ala-row > input {
  margin-top: 2px;
}
.ala-main {
  flex: 1;
  min-width: 0;
}
.ala-pair {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.ala-phrase {
  font-weight: 600;
  color: var(--accent-strong);
}
.ala-arrow {
  color: var(--text-mute);
}
.ala-snippet {
  margin-top: 3px;
  font-size: 11.5px;
  line-height: 1.5;
}
.ala-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
}
.icon-btn {
  padding: 4px 8px;
}
</style>
