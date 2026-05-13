<template>
  <div class="ai-panel">
    <div class="ai-head row">
      <strong>{{ t('ai.title') }}</strong>
      <button
        v-if="currentHtml && currentHtml.trim()"
        class="ghost pick-btn"
        :class="{ active: pickMode }"
        :title="t('ai.pickElement')"
        @click="$emit('toggle-pick')"
      ><span class="ico" aria-hidden="true">◎</span>{{ t('ai.pick') }}</button>
      <span class="muted" style="margin-left:auto; font-size:12px;">
        {{ currentHtml && currentHtml.trim() ? t('ai.hintEdit') : t('ai.hintNew') }}
      </span>
    </div>

    <div ref="logEl" class="ai-log scroll">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="msg-role">{{ m.role === 'user' ? 'You' : 'AI' }}</div>
        <div class="msg-body">{{ m.text }}</div>
        <div v-if="m.attachedState" class="msg-tag">＋ {{ t('ai.stateAttached') }}</div>
        <div v-if="m.attachedPick" class="msg-tag">＋ {{ t('ai.pickAttached', { tag: m.attachedPick }) }}</div>
        <div v-if="m.role === 'assistant' && m.html" class="msg-actions">
          <button class="ghost" @click="apply(m.html)" :title="t('ai.apply')">
            <span class="ico" aria-hidden="true">↩</span>{{ t('ai.apply') }}
          </button>
        </div>
      </div>
      <div v-if="streaming" class="msg assistant streaming">
        <div class="msg-role">AI {{ t('ai.applying') }}<span class="dots" aria-hidden="true"></span></div>
      </div>
    </div>

    <div v-if="disabled" class="ai-disabled muted">{{ disabledReason }}</div>

    <div v-if="interfaceState != null" class="state-chip">
      <span>✦ {{ t('ai.stateCaptured') }}</span>
      <button class="ghost x" @click="$emit('clear-state')" title="clear">×</button>
    </div>

    <div v-if="pickedElement" class="pick-chip">
      <span class="pick-ico">◎</span>
      <code class="pick-tag">{{ pickedTagLabel }}</code>
      <span v-if="pickedElement.text" class="pick-text">{{ pickedElement.text }}</span>
      <button class="ghost x" @click="$emit('clear-picked')" :title="t('ai.clearPicked')">×</button>
    </div>

    <form class="ai-input" @submit.prevent="send">
      <textarea
        v-model="prompt"
        :placeholder="t('ai.placeholder')"
        :disabled="disabled"
        rows="4"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <div class="row" style="justify-content:flex-end; gap:6px;">
        <button v-if="streaming" type="button" class="ghost" @click="stop">{{ t('ai.stop') }}</button>
        <button type="submit" class="primary" :disabled="disabled || streaming || (!prompt.trim() && interfaceState == null && !pickedElement)">
          {{ t('ai.send') }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { streamChat } from '@/api/ai'
import { pushToast } from '@/composables/useToast'

const props = defineProps({
  currentHtml: { type: String, default: '' },
  path: { type: String, default: '' },
  interfaceState: { default: null },
  pickedElement: { type: Object, default: null },
  pickMode: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  disabledReason: { type: String, default: '' }
})
const emit = defineEmits(['apply', 'clear-state', 'toggle-pick', 'clear-picked'])
const { t } = useI18n()

const prompt = ref('')
const messages = ref([]) // {role:'user'|'assistant', text, html?, attachedState?}
const streaming = ref(false)
const logEl = ref(null)
let controller = null

function scrollDown() {
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

// "<div.card#cool>"-style label for the picked-element chip
const pickedTagLabel = computed(() => {
  const p = props.pickedElement
  if (!p) return ''
  const tag = (p.tagName || 'el').toLowerCase()
  const id = p.id ? '#' + p.id : ''
  const firstClass = (p.classes || '').trim().split(/\s+/).filter(Boolean)[0]
  return `<${tag}${id}${firstClass ? '.' + firstClass : ''}>`
})

async function send() {
  if (props.disabled || streaming.value) return
  const p = prompt.value.trim()
  const attached = props.interfaceState
  const picked = props.pickedElement
  if (!p && attached == null && !picked) {
    pushToast(t('ai.needPrompt'))
    return
  }
  const placeholder = p || (picked ? '(围绕选中元素)' : '(只发送界面状态)')
  messages.value.push({
    role: 'user',
    text: placeholder,
    attachedState: attached != null,
    attachedPick: picked ? pickedTagLabel.value : null
  })
  prompt.value = ''
  // picked is consumed on send — clear it now so the user sees the chip vanish
  if (picked) emit('clear-picked')
  streaming.value = true
  scrollDown()

  controller = new AbortController()
  await streamChat(
    {
      prompt: p,
      currentHtml: props.currentHtml,
      path: props.path,
      ...(attached != null ? { interfaceState: attached } : {}),
      ...(picked ? { pickedElement: picked } : {})
    },
    {
      signal: controller.signal,
      // streaming chunks are discarded — the panel only shows an animated "生成中"
      onDone: ({ html, mode, applied, failed }) => {
        streaming.value = false
        const skipped = (failed && failed.length) || 0
        const n = applied || 0
        const changed = !!html && html !== props.currentHtml
        let text
        if (mode === 'patch') {
          if (n > 0) text = skipped ? `已应用 ${n} 处修改（${skipped} 处没对上原文，已跳过）` : `已应用 ${n} 处修改`
          else text = skipped ? `${skipped} 处修改都没对上原文，文档未改动` : '（模型没有给出改动）'
        } else if (mode === 'noop') {
          text = '（模型没有改动文档）'
        } else {
          text = changed ? '已生成新文档' : '（无变化）'
        }
        messages.value.push({ role: 'assistant', text, html: changed ? html : '' })
        if (changed) emit('apply', html)
        if (skipped) pushToast(`${skipped} 处片段没对上当前文档，已跳过 —— 可以让 AI 重新整篇生成`, 'error')
        scrollDown()
      },
      onError: (msg) => {
        streaming.value = false
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
}

function apply(html) {
  emit('apply', html)
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
.msg.streaming .msg-role { text-transform: none; letter-spacing: 0; font-size: 12.5px; color: var(--accent); }
.dots {
  display: inline-block; width: 1.5em; text-align: left; vertical-align: baseline;
}
.dots::after {
  content: '...';
  display: inline-block;
  animation: phial-dots 1.2s steps(4, end) infinite;
  clip-path: inset(0 100% 0 0);
}
@keyframes phial-dots {
  0%   { clip-path: inset(0 100% 0 0); }
  25%  { clip-path: inset(0 66% 0 0); }
  50%  { clip-path: inset(0 33% 0 0); }
  75%  { clip-path: inset(0 0 0 0); }
  100% { clip-path: inset(0 100% 0 0); }
}
.msg-actions { display: flex; gap: 6px; margin-top: 2px; }
.msg-actions button { display: inline-flex; align-items: center; gap: 5px; padding: 4px 9px; font-size: 12px; }
.msg-actions .ico { color: var(--accent); font-size: 13px; line-height: 1; }
.ai-disabled { padding: 8px 12px; font-size: 12px; background: #fff7ed; border-top: 1px solid var(--border); }
.state-chip {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px; font-size: 12px;
  background: #f5f3ff; color: #5b21b6; border-top: 1px solid var(--border);
}
.state-chip span { flex: 1; }
.state-chip .x { padding: 1px 7px; color: #6b21a8; }

.pick-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; font-size: 12px;
  color: var(--text-dim); border-color: var(--border);
}
.pick-btn .ico { font-size: 14px; line-height: 1; color: var(--text-dim); }
.pick-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
.pick-btn.active .ico { color: var(--accent); animation: pick-pulse 1.4s ease-in-out infinite; }
@keyframes pick-pulse {
  0%, 100% { opacity: 0.5; }
  50%      { opacity: 1; }
}
.pick-chip {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px; font-size: 12px;
  background: #f5f3ff; color: #5b21b6; border-top: 1px solid var(--border);
}
.pick-chip .pick-ico { color: var(--accent); }
.pick-chip .pick-tag { font-family: var(--mono); font-size: 11.5px; color: var(--accent); white-space: nowrap; flex: none; }
.pick-chip .pick-text {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-dim);
}
.pick-chip .x { padding: 1px 7px; color: #6b21a8; margin-left: auto; }
.ai-input { padding: 10px 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
.ai-input textarea { resize: vertical; width: 100%; }
</style>
