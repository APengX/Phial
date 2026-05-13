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
      <button
        class="ghost new-chat-btn"
        :title="t('ai.newChat')"
        :disabled="streaming || !messages.length"
        @click="newChat"
      ><span class="ico" aria-hidden="true">＋</span>{{ t('ai.newChat') }}</button>
      <span class="muted hint" :title="hintLong">{{ hintShort }}</span>
    </div>

    <div ref="logEl" class="ai-log scroll">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="[m.role, { 'is-chat': m.mode === 'chat' }]">
        <div class="msg-role">
          {{ m.role === 'user' ? 'You' : 'AI' }}
          <span v-if="m.mode === 'chat'" class="role-tag">chat</span>
        </div>
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
        <div class="msg-role">
          AI
          <span v-if="mode === 'chat'" class="role-tag">chat</span>
          <template v-if="mode === 'agent' || !streamText">
            {{ t('ai.applying') }}<span class="dots" aria-hidden="true"></span>
          </template>
        </div>
        <div v-if="mode === 'chat' && streamText" class="msg-body">{{ streamText }}<span class="caret" aria-hidden="true"></span></div>
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

    <div v-if="path" class="ctx-chip" :class="{ on: contextCount > 0 }">
      <button
        class="ghost ctx-btn"
        :title="t('ai.ctxChipTip')"
        @click="$emit('open-context')"
      >
        <span aria-hidden="true">📎</span>
        {{ t('ai.ctxChip') }}
        <span class="ctx-n">{{ contextCount }}</span>
      </button>
    </div>

    <div class="ai-input" :style="{ height: inputHeight + 'px' }">
      <div
        class="height-grip"
        :title="t('ai.dragHeight')"
        @mousedown.prevent="startHeightDrag"
      ><span class="grip-bar"></span></div>
      <form class="ai-input-inner" @submit.prevent="send">
        <textarea
          ref="taRef"
          v-model="prompt"
          :placeholder="t('ai.placeholder')"
          :disabled="disabled"
          @keydown.enter.exact.prevent="send"
        ></textarea>
        <div class="ai-input-foot row">
          <div class="mode-switch" role="tablist" :aria-label="t('ai.modeAgent') + ' / ' + t('ai.modeChat')">
            <button
              type="button" role="tab"
              :class="{ active: mode === 'agent' }"
              :aria-selected="mode === 'agent'"
              :title="t('ai.modeAgentTip')"
              :disabled="streaming"
              @click="setMode('agent')"
            >{{ t('ai.modeAgent') }}</button>
            <button
              type="button" role="tab"
              :class="{ active: mode === 'chat' }"
              :aria-selected="mode === 'chat'"
              :title="t('ai.modeChatTip')"
              :disabled="streaming"
              @click="setMode('chat')"
            >{{ t('ai.modeChat') }}</button>
          </div>
          <div class="row" style="margin-left:auto; gap:6px;">
            <button v-if="streaming" type="button" class="ghost" @click="stop">{{ t('ai.stop') }}</button>
            <button type="submit" class="primary" :disabled="sendDisabled">
              {{ t('ai.send') }}
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { streamChat } from '@/api/ai'
import { pushToast } from '@/composables/useToast'

const props = defineProps({
  currentHtml: { type: String, default: '' },
  path: { type: String, default: '' },
  interfaceState: { default: null },
  pickedElement: { type: Object, default: null },
  pickMode: { type: Boolean, default: false },
  contextCount: { type: Number, default: 0 },
  disabled: { type: Boolean, default: false },
  disabledReason: { type: String, default: '' }
})
const emit = defineEmits(['apply', 'clear-state', 'toggle-pick', 'clear-picked', 'open-context'])
const { t } = useI18n()

// Messages keep `mode` on each entry so a doc's transcript can mix agent + chat
// turns and stay readable when reloaded.
const prompt = ref('')
const messages = ref([]) // {role, text, mode, html?, attachedState?, attachedPick?}
const streaming = ref(false)
const streamText = ref('') // live-updating assistant text while a chat reply streams
const logEl = ref(null)
const taRef = ref(null)
const mode = ref('agent') // 'agent' | 'chat' — persisted per panel
let controller = null

// ---- transcript persistence (per document path) -------------------------
const HISTORY_KEY_PREFIX = 'phial.aiHistory:'
const MODE_KEY = 'phial.aiMode'
const INPUT_HEIGHT_KEY = 'phial.aiInputHeight'
const HISTORY_LIMIT = 200       // cap stored turns so localStorage doesn't bloat
const HISTORY_SEND_LIMIT = 20   // how many recent turns we send to the model

function historyKey(path) {
  return HISTORY_KEY_PREFIX + (path || '__none__')
}

function loadHistory(path) {
  try {
    const raw = localStorage.getItem(historyKey(path))
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

function saveHistory() {
  if (!props.path) return
  try {
    const trimmed = messages.value.slice(-HISTORY_LIMIT)
    localStorage.setItem(historyKey(props.path), JSON.stringify(trimmed))
  } catch {
    /* quota errors etc. — non-fatal */
  }
}

function clearStoredHistory(path) {
  try { localStorage.removeItem(historyKey(path)) } catch { /* ignore */ }
}

// Initial mode from last session.
try {
  const saved = localStorage.getItem(MODE_KEY)
  if (saved === 'chat' || saved === 'agent') mode.value = saved
} catch { /* ignore */ }

// ---- input area height (top-edge drag handle) ---------------------------
const INPUT_MIN = 96
const INPUT_MAX = 520
const clampHeight = (n) => Math.max(INPUT_MIN, Math.min(INPUT_MAX, Number(n) || 160))
const inputHeight = ref(clampHeight(localStorage.getItem(INPUT_HEIGHT_KEY) || 160))
let heightDrag = null

function startHeightDrag(e) {
  heightDrag = { startY: e.clientY, startH: inputHeight.value }
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onHeightDrag)
  window.addEventListener('mouseup', endHeightDrag)
}
function onHeightDrag(e) {
  if (!heightDrag) return
  // dragging up grows the input; clientY decreases -> delta is positive
  inputHeight.value = clampHeight(heightDrag.startH + (heightDrag.startY - e.clientY))
}
function endHeightDrag() {
  if (!heightDrag) return
  heightDrag = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onHeightDrag)
  window.removeEventListener('mouseup', endHeightDrag)
  try { localStorage.setItem(INPUT_HEIGHT_KEY, String(inputHeight.value)) } catch { /* ignore */ }
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onHeightDrag)
  window.removeEventListener('mouseup', endHeightDrag)
})

// ---- send-button disabled state ----------------------------------------
// Chat mode always needs a real question typed in: an attached picked-element
// or interface state alone is meaningless ("answer what?"). Agent mode can
// send with just an attached state / pick — that means "modify this".
const sendDisabled = computed(() => {
  if (props.disabled || streaming.value) return true
  if (mode.value === 'chat') return !prompt.value.trim()
  return !prompt.value.trim() && props.interfaceState == null && !props.pickedElement
})

// ---- hints --------------------------------------------------------------
const hintShort = computed(() => {
  if (mode.value === 'chat') return t('ai.modeChatTip')
  return props.currentHtml && props.currentHtml.trim() ? t('ai.hintEdit') : t('ai.hintNew')
})
const hintLong = computed(() => hintShort.value)

// "<div.card#cool>"-style label for the picked-element chip
const pickedTagLabel = computed(() => {
  const p = props.pickedElement
  if (!p) return ''
  const tag = (p.tagName || 'el').toLowerCase()
  const id = p.id ? '#' + p.id : ''
  const firstClass = (p.classes || '').trim().split(/\s+/).filter(Boolean)[0]
  return `<${tag}${id}${firstClass ? '.' + firstClass : ''}>`
})

function scrollDown() {
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

function setMode(next) {
  if (streaming.value) return
  if (next !== 'agent' && next !== 'chat') return
  if (mode.value === next) return
  mode.value = next
  try { localStorage.setItem(MODE_KEY, next) } catch { /* ignore */ }
}

function newChat() {
  if (streaming.value) return
  if (!messages.value.length) return
  if (!window.confirm(t('ai.newChatConfirm'))) return
  messages.value = []
  streamText.value = ''
  saveHistory()
}

async function send() {
  if (props.disabled || streaming.value) return
  const p = prompt.value.trim()
  const attached = props.interfaceState
  const picked = props.pickedElement
  const currentMode = mode.value
  // Chat mode insists on a typed question — attached state alone isn't a "ask".
  if (currentMode === 'chat' ? !p : (!p && attached == null && !picked)) {
    pushToast(t('ai.needPrompt'))
    return
  }
  const placeholder = p || (picked ? '(围绕选中元素)' : '(只发送界面状态)')
  messages.value.push({
    role: 'user',
    mode: currentMode,
    text: placeholder,
    attachedState: attached != null,
    attachedPick: picked ? pickedTagLabel.value : null
  })
  prompt.value = ''
  // picked is consumed on send — clear it now so the user sees the chip vanish
  if (picked) emit('clear-picked')
  streaming.value = true
  streamText.value = ''
  scrollDown()

  // For chat mode, send recent turns so the model has continuity.
  const history = currentMode === 'chat'
    ? messages.value
        .slice(0, -1) // exclude the just-pushed user turn (we send it as `prompt`)
        .slice(-HISTORY_SEND_LIMIT)
        .map((m) => ({ role: m.role, text: m.text }))
    : undefined

  controller = new AbortController()
  await streamChat(
    {
      prompt: p,
      currentHtml: props.currentHtml,
      path: props.path,
      mode: currentMode,
      ...(history ? { history } : {}),
      ...(attached != null ? { interfaceState: attached } : {}),
      ...(picked ? { pickedElement: picked } : {})
    },
    {
      signal: controller.signal,
      onDelta: (piece) => {
        // Only chat mode shows live text; agent-mode deltas are HTML fragments
        // mid-stream and would render as garbage in the panel.
        if (currentMode === 'chat' && piece) {
          streamText.value += piece
          scrollDown()
        }
      },
      onDone: (result) => {
        streaming.value = false
        if (currentMode === 'chat') {
          const text = (result.text || streamText.value || '').trim()
          messages.value.push({
            role: 'assistant',
            mode: 'chat',
            text: text || '(空回复)'
          })
          streamText.value = ''
          saveHistory()
          scrollDown()
          return
        }
        // agent mode
        const { html, mode: replyMode, applied, failed } = result
        const skipped = (failed && failed.length) || 0
        const n = applied || 0
        const changed = !!html && html !== props.currentHtml
        let text
        if (replyMode === 'patch') {
          if (n > 0) text = skipped ? `已应用 ${n} 处修改（${skipped} 处没对上原文，已跳过）` : `已应用 ${n} 处修改`
          else text = skipped ? `${skipped} 处修改都没对上原文，文档未改动` : '（模型没有给出改动）'
        } else if (replyMode === 'noop') {
          text = '（模型没有改动文档）'
        } else {
          text = changed ? '已生成新文档' : '（无变化）'
        }
        messages.value.push({ role: 'assistant', mode: 'agent', text, html: changed ? html : '' })
        saveHistory()
        if (changed) emit('apply', html)
        if (skipped) pushToast(`${skipped} 处片段没对上当前文档，已跳过 —— 可以让 AI 重新整篇生成`, 'error')
        scrollDown()
      },
      onError: (msg) => {
        streaming.value = false
        streamText.value = ''
        messages.value.push({ role: 'assistant', mode: currentMode, text: t('ai.error', { msg }) })
        saveHistory()
        pushToast(t('ai.error', { msg }), 'error')
        scrollDown()
      }
    }
  )
}

function stop() {
  controller?.abort()
  streaming.value = false
  // If the user interrupted a chat reply mid-stream, keep what we got so far
  // as a real message so the conversation makes sense afterwards.
  if (streamText.value.trim()) {
    messages.value.push({ role: 'assistant', mode: 'chat', text: streamText.value.trim() + ' …(已中断)' })
    saveHistory()
  }
  streamText.value = ''
}

function apply(html) {
  emit('apply', html)
}

// Called by the parent when the rendered document fires phial.sendToAgent(...).
// That hook is meant to drive a real edit, so force agent mode regardless of
// what the user last selected.
function submitWith(text) {
  prompt.value = String(text || '')
  if (mode.value !== 'agent') setMode('agent')
  if (!streaming.value && !props.disabled) send()
}

// Switching documents -> swap to that doc's transcript instead of clearing.
watch(
  () => props.path,
  (next, prev) => {
    if (streaming.value) stop()
    // The just-shown transcript may have been mutated since last save — flush.
    if (prev && messages.value.length) {
      try { localStorage.setItem(historyKey(prev), JSON.stringify(messages.value.slice(-HISTORY_LIMIT))) } catch { /* ignore */ }
    }
    messages.value = loadHistory(next)
    streamText.value = ''
    scrollDown()
  },
  { immediate: true }
)

defineExpose({ submitWith })
</script>

<style scoped>
.ai-panel { display: flex; flex-direction: column; height: 100%; background: var(--bg-panel); }
.ai-head { padding: 10px 12px; border-bottom: 1px solid var(--border); gap: 8px; }
.ai-head .hint { margin-left: auto; font-size: 12px; max-width: 50%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-log { flex: 1; padding: 12px; display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.msg { display: flex; flex-direction: column; gap: 4px; }
.msg-role { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; display: flex; align-items: center; gap: 6px; }
.role-tag {
  font-size: 10px; padding: 0 5px; border-radius: 999px; text-transform: lowercase; letter-spacing: 0;
  background: var(--bg-soft); color: var(--text-dim);
}
.msg.is-chat .role-tag { background: #ecfeff; color: #0e7490; }
.msg-body { font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.msg.user .msg-body {
  background: var(--accent-soft); color: #4c1d95; padding: 8px 10px; border-radius: 8px; align-self: flex-start;
}
.msg.user.is-chat .msg-body { background: #ecfeff; color: #155e75; }
.msg-tag { font-size: 11px; color: var(--accent); align-self: flex-start; }
.msg.streaming .msg-role { text-transform: none; letter-spacing: 0; font-size: 12.5px; color: var(--accent); }
.caret {
  display: inline-block; width: 6px; height: 1em; background: var(--accent); margin-left: 2px; vertical-align: -2px;
  animation: phial-caret 1s steps(2, end) infinite;
}
@keyframes phial-caret {
  50% { opacity: 0; }
}
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
.new-chat-btn {
  display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; font-size: 12px;
  color: var(--text-dim);
}
.new-chat-btn .ico { font-size: 13px; line-height: 1; }
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

/* Context picker chip — sits above the input, neutral when empty, accent when not. */
.ctx-chip {
  display: flex; padding: 6px 12px; border-top: 1px solid var(--border);
  background: var(--bg-panel);
}
.ctx-chip.on { background: var(--accent-soft); }
.ctx-btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px; font-size: 12px;
  color: var(--text-dim);
}
.ctx-chip.on .ctx-btn { color: var(--accent); border-color: var(--accent); }
.ctx-n {
  font-variant-numeric: tabular-nums; min-width: 1ch; text-align: right;
  font-size: 11.5px; padding: 0 5px; border-radius: 999px; background: var(--bg-soft);
}
.ctx-chip.on .ctx-n { background: #fff; color: var(--accent); }

/* ---- input area with top-edge drag handle --------------------------- */
.ai-input {
  position: relative;
  border-top: 1px solid var(--border);
  display: flex; flex-direction: column;
  flex: none;
}
.height-grip {
  position: absolute; left: 0; right: 0; top: -4px; height: 9px;
  cursor: row-resize; z-index: 5;
  display: flex; align-items: center; justify-content: center;
}
.height-grip .grip-bar {
  display: block; width: 36px; height: 3px; border-radius: 2px;
  background: var(--border); transition: background 0.12s;
}
.height-grip:hover .grip-bar { background: var(--accent); }
.ai-input-inner {
  display: flex; flex-direction: column; gap: 6px;
  padding: 10px 12px; height: 100%; min-height: 0;
}
.ai-input-inner textarea {
  flex: 1; min-height: 0; width: 100%; resize: none;
}
.ai-input-foot { gap: 6px; align-items: center; }
.mode-switch {
  display: inline-flex; border: 1px solid var(--border); border-radius: 999px; overflow: hidden; background: var(--bg-panel);
}
.mode-switch button {
  border: 0; border-radius: 0; background: transparent; color: var(--text-dim);
  padding: 3px 10px; font-size: 12px; line-height: 1.4;
}
.mode-switch button + button { border-left: 1px solid var(--border); }
.mode-switch button.active { background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.mode-switch button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
