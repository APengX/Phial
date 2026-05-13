<template>
  <div v-if="modelValue" class="overlay" @click.self="close">
    <div class="modal">
      <header class="m-head">
        <strong>{{ t('settings.title') }}</strong>
        <button class="ghost x" @click="close">×</button>
      </header>

      <div v-if="loading" class="m-body muted">{{ t('common.loading') }}</div>

      <div v-else class="m-body">
        <p v-if="error" class="m-error">{{ error }}</p>

        <section>
          <h3>{{ t('settings.agent') }}</h3>
          <p class="muted hint">{{ t('settings.agentHint') }}</p>
          <label
            v-for="opt in providerOptions"
            :key="opt.id"
            class="prov"
            :class="{ active: provider === opt.id }"
          >
            <input type="radio" :value="opt.id" v-model="provider" />
            <span class="p-name">{{ opt.name }}</span>
            <span v-if="opt.isBuiltin" class="badge" :class="opt.ready ? 'ok' : 'warn'">
              {{ opt.ready ? t('settings.builtinReady', { model: opt.model }) : t('settings.builtinMissing') }}
            </span>
            <template v-else>
              <span class="badge" :class="opt.installed ? 'ok' : 'warn'">
                {{ opt.installed ? t('settings.installed') : t('settings.notInstalled') }}
              </span>
              <span v-if="opt.version" class="ver">{{ opt.version }}</span>
              <code v-if="opt.path" class="ver path">{{ opt.path }}</code>
            </template>
          </label>
        </section>

        <section v-if="selectedDetected && !selectedDetected.installed" class="warnbox">
          {{ t('settings.notInstalledWarn', { bin: selectedDetected.bin }) }}
          <a :href="selectedDetected.docUrl" target="_blank" rel="noreferrer">{{ t('settings.install') }} ↗</a>
        </section>

        <section>
          <h3>{{ t('settings.model') }}</h3>
          <input
            v-if="!isBuiltin"
            v-model="model"
            class="full"
            :placeholder="selectedDetected ? selectedDetected.modelLabel : 'model'"
          />
          <div v-else class="readonly">
            {{ builtin.model || '—' }}
            <span class="muted"> · {{ t('settings.builtinModelNote') }}</span>
          </div>
        </section>

        <section>
          <h3>{{ t('settings.env') }}</h3>
          <p class="muted hint">{{ isBuiltin ? t('settings.envBuiltinNote') : t('settings.envHint') }}</p>
          <template v-if="!isBuiltin">
            <div v-for="(row, i) in envRows" :key="i" class="env-row">
              <input v-model="row.key" class="env-k" placeholder="KEY" spellcheck="false" />
              <input v-model="row.value" class="env-v" placeholder="value" spellcheck="false" />
              <button class="ghost x" @click="envRows.splice(i, 1)">×</button>
            </div>
            <div class="env-actions">
              <button class="ghost" @click="envRows.push({ key: '', value: '' })">＋ {{ t('settings.addVar') }}</button>
              <span v-if="selectedDetected && selectedDetected.envHints && selectedDetected.envHints.length" class="suggest">
                {{ t('settings.suggested') }}:
                <button
                  v-for="h in selectedDetected.envHints"
                  :key="h.key"
                  class="chip"
                  :title="h.desc"
                  @click="addHint(h.key)"
                >{{ h.key }}</button>
              </span>
            </div>
          </template>
        </section>
      </div>

      <footer class="m-foot">
        <span class="muted run-hint" v-if="!isBuiltin && selectedDetected && selectedDetected.installed">
          {{ t('settings.willRun') }}: <code>{{ selectedDetected.bin }} …</code>
        </span>
        <span class="spacer"></span>
        <button class="ghost" @click="close">{{ t('common.cancel') }}</button>
        <button class="primary" :disabled="saving" @click="save">{{ saving ? '…' : t('settings.save') }}</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAgents, setAgent } from '@/api/agents'
import { pushToast } from '@/composables/useToast'

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue', 'saved'])
const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const detected = ref([])
const builtin = ref({ id: 'builtin', name: '内置 LLM API', configured: false, model: '' })
const current = ref({ provider: 'builtin', model: '', env: {} })
const provider = ref('builtin')
const model = ref('')
const envRows = ref([])

const isBuiltin = computed(() => provider.value === 'builtin')
const selectedDetected = computed(() => detected.value.find((d) => d.id === provider.value) || null)
const providerOptions = computed(() => [
  { id: 'builtin', name: builtin.value.name, isBuiltin: true, ready: builtin.value.configured, model: builtin.value.model },
  ...detected.value.map((d) => ({ ...d, isBuiltin: false }))
])

function close() {
  emit('update:modelValue', false)
}

function loadCurrentInto() {
  // when the picked provider matches what's saved, restore its model/env
  if (provider.value === current.value.provider) {
    model.value = current.value.model || ''
    envRows.value = Object.entries(current.value.env || {}).map(([k, v]) => ({ key: k, value: v }))
  } else {
    model.value = ''
    envRows.value = []
  }
  if (!isBuiltin.value && envRows.value.length === 0) envRows.value = [{ key: '', value: '' }]
}

function addHint(key) {
  if (envRows.value.some((r) => r.key === key)) return
  // fill the first empty row, else append
  const empty = envRows.value.find((r) => !r.key.trim())
  if (empty) empty.key = key
  else envRows.value.push({ key, value: '' })
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    loading.value = true
    error.value = ''
    try {
      const data = await getAgents()
      detected.value = data.detected || []
      builtin.value = data.builtin || builtin.value
      current.value = data.current || current.value
      provider.value = current.value.provider || 'builtin'
      loadCurrentInto()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }
)

watch(provider, () => loadCurrentInto())

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload = { provider: provider.value }
    if (!isBuiltin.value) {
      payload.model = model.value.trim()
      payload.env = {}
      envRows.value.forEach((r) => {
        const k = r.key.trim()
        if (k) payload.env[k] = r.value
      })
    }
    const res = await setAgent(payload)
    pushToast(t('settings.saved', { name: res.active?.name || provider.value }), 'success')
    emit('saved', res.active)
    close()
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0; background: rgba(15, 19, 28, 0.4); z-index: 500;
  display: flex; align-items: flex-start; justify-content: center; padding: 6vh 16px;
}
.modal {
  background: var(--bg-panel); border-radius: 12px; width: 560px; max-width: 100%; max-height: 88vh;
  display: flex; flex-direction: column; box-shadow: 0 24px 64px rgba(0, 0, 0, 0.28);
}
.m-head { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.m-head strong { flex: 1; }
.x { padding: 1px 8px; font-size: 1.1rem; line-height: 1; }
.m-body { padding: 14px 16px; overflow: auto; }
.m-body section { margin-bottom: 18px; }
.m-body h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); margin: 0 0 8px; }
.hint { font-size: 12px; margin: -2px 0 8px; }
.m-error { background: #fef2f2; color: #b91c1c; padding: 7px 10px; border-radius: 7px; font-size: 13px; margin: 0 0 12px; }

.prov {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: 7px; cursor: pointer; flex-wrap: wrap;
}
.prov.active { border-color: var(--accent); background: #faf5ff; }
.p-name { font-weight: 500; }
.badge { font-size: 11px; padding: 1px 7px; border-radius: 999px; }
.badge.ok { background: #ecfdf5; color: #047857; }
.badge.warn { background: #fffbeb; color: #b45309; }
.ver { font-size: 11px; color: var(--text-dim); }
.ver.path { font-family: var(--mono); }

.warnbox {
  background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: 8px 10px; border-radius: 7px;
  font-size: 12.5px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.warnbox a { margin-left: auto; }

.full { width: 100%; }
.readonly {
  font-family: var(--mono); font-size: 12.5px; background: var(--bg-soft); padding: 7px 10px; border-radius: 7px;
}

.env-row { display: flex; gap: 6px; margin-bottom: 6px; align-items: center; }
.env-k { width: 38%; font-family: var(--mono); }
.env-v { flex: 1; font-family: var(--mono); }
.env-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 4px; }
.suggest { font-size: 12px; color: var(--text-dim); }
.chip {
  font-size: 11.5px; padding: 1px 8px; border-radius: 999px; margin-left: 5px;
  border-color: var(--accent-soft); background: var(--accent-soft); color: var(--accent);
}

.m-foot { display: flex; align-items: center; gap: 8px; padding: 11px 16px; border-top: 1px solid var(--border); }
.m-foot .spacer { flex: 1; }
.run-hint { font-size: 11.5px; }
.run-hint code { font-family: var(--mono); }
</style>
