<template>
  <div class="ai-panel">
    <div class="ai-head row">
      <strong>{{ t('ai.title') }}</strong>
      <span class="muted" style="margin-left:auto; font-size:12px;">
        {{ currentHtml && currentHtml.trim() ? t('ai.hintEdit') : t('ai.hintNew') }}
      </span>
    </div>

    <div ref="logEl" class="ai-log scroll">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="msg-role">{{ m.role === 'user' ? 'You' : 'AI' }}</div>
        <div class="msg-body">{{ m.text }}</div>
        <div v-if="m.attachedState" class="msg-tag">＋ {{ t('ai.stateAttached') }}</div>
        <div v-if="m.role === 'assistant' && m.html" class="msg-actions">
          <button class="primary" @click="apply(m.html)">{{ t('ai.apply') }}</button>
          <button class="ghost" @click="discard">{{ t('ai.discard') }}</button>
        </div>
      </div>
      <div v-if="streaming" class="msg assistant streaming">
        <div class="msg-role">AI · {{ t('ai.applying') }}</div>
        <pre class="msg-body stream">{{ streamText || '…' }}</pre>
      </div>
    </div>

    <div v-if="disabled" class="ai-disabled muted">{{ disabledReason }}</div>

    <div v-if="interfaceState != null" class="state-chip">
      <span>✦ {{ t('ai.stateCaptured') }}</span>
      <button class="ghost x" @click="$emit('clear-state')" title="clear">×</button>
    </div>

    <form class="ai-input" @submit.prevent="send">
      <textarea
        v-model="prompt"
        :placeholder="t('ai.placeholder')"
        :disabled="disabled"
        rows="3"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <div class="row" style="justify-content:flex-end; gap:6px;">
        <button v-if="streaming" type="button" class="ghost" @click="stop">{{ t('ai.stop') }}</button>
        <button type="submit" class="primary" :disabled="disabled || streaming || (!prompt.trim() && interfaceState == null)">
          {{ t('ai.send') }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { streamChat } from '@/api/ai'
import { pushToast } from '@/composables/useToast'

const props = defineProps({
  currentHtml: { type: String, default: '' },
  path: { type: String, default: '' },
  interfaceState: { default: null },
  disabled: { type: Boolean, default: false },
  disabledReason: { type: String, default: '' }
})
const emit = defineEmits(['preview', 'apply', 'clear-state'])
const { t } = useI18n()

const prompt = ref('')
const messages = ref([]) // {role:'user'|'assistant', text, html?, attachedState?}
const streaming = ref(false)
const streamText = ref('')
const logEl = ref(null)
let controller = null

function scrollDown() {
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

async function send() {
  if (props.disabled || streaming.value) return
  const p = prompt.value.trim()
  if (!p && props.interfaceState == null) {
    pushToast(t('ai.needPrompt'))
    return
  }
  const attached = props.interfaceState
  messages.value.push({ role: 'user', text: p || '(只发送界面状态)', attachedState: attached != null })
  prompt.value = ''
  streaming.value = true
  streamText.value = ''
  scrollDown()

  controller = new AbortController()
  await streamChat(
    {
      prompt: p,
      currentHtml: props.currentHtml,
      path: props.path,
      ...(attached != null ? { interfaceState: attached } : {})
    },
    {
      signal: controller.signal,
      onDelta: (chunk) => {
        streamText.value += chunk
        scrollDown()
      },
      onDone: ({ html }) => {
        streaming.value = false
        messages.value.push({
          role: 'assistant',
          text: html ? '已生成 —— 预览已切换到该结果。' : '（模型没有返回可用的 HTML）',
          html: html || ''
        })
        streamText.value = ''
        if (html) emit('preview', html)
        scrollDown()
      },
      onError: (msg) => {
        streaming.value = false
        streamText.value = ''
        messages.value.push({ role: 'assistant', text: t('ai.error', { msg }) })
        pushToast(t('ai.error', { msg }), 'error')
        scrollDown()
      }
    }
  )
}

function stop() {
  controller?.abort()
  streaming.value = false
  streamText.value = ''
}

function apply(html) {
  emit('apply', html)
}
function discard() {
  emit('preview', null)
}

// Called by the parent when the rendered document fires phial.sendToAgent(...)
function submitWith(text) {
  prompt.value = String(text || '')
  if (!streaming.value && !props.disabled) send()
}

watch(
  () => props.path,
  () => {
    messages.value = []
    streamText.value = ''
    if (streaming.value) stop()
  }
)

defineExpose({ submitWith })
</script>

<style scoped>
.ai-panel { display: flex; flex-direction: column; height: 100%; background: var(--bg-panel); }
.ai-head { padding: 10px 12px; border-bottom: 1px solid var(--border); }
.ai-log { flex: 1; padding: 12px; display: flex; flex-direction: column; gap: 14px; }
.msg { display: flex; flex-direction: column; gap: 4px; }
.msg-role { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; }
.msg-body { font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.msg.user .msg-body {
  background: var(--accent-soft); color: #4c1d95; padding: 8px 10px; border-radius: 8px; align-self: flex-start;
}
.msg-tag { font-size: 11px; color: var(--accent); align-self: flex-start; }
.msg-body.stream {
  background: var(--bg-soft); padding: 8px 10px; border-radius: 8px; font-family: var(--mono);
  font-size: 11.5px; max-height: 220px; overflow: auto; margin: 0;
}
.msg-actions { display: flex; gap: 6px; margin-top: 2px; }
.ai-disabled { padding: 8px 12px; font-size: 12px; background: #fff7ed; border-top: 1px solid var(--border); }
.state-chip {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px; font-size: 12px;
  background: #f5f3ff; color: #5b21b6; border-top: 1px solid var(--border);
}
.state-chip span { flex: 1; }
.state-chip .x { padding: 1px 7px; color: #6b21a8; }
.ai-input { padding: 10px 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
.ai-input textarea { resize: vertical; width: 100%; }
</style>
