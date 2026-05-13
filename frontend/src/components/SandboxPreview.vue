<template>
  <iframe
    ref="frame"
    class="sandbox-frame"
    :sandbox="sandboxAttr"
    allow="clipboard-write"
    referrerpolicy="no-referrer"
    @load="onFrameLoad"
  ></iframe>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'

const props = defineProps({
  html: { type: String, default: '' },
  // { allowScripts: boolean, allowExternal: boolean }
  settings: { type: Object, default: () => ({ allowScripts: true, allowExternal: false }) },
  // optional data pushed into the document (delivered to window.__phialOnData / 'phial:data' event)
  incomingData: { default: null }
})
const emit = defineEmits(['state', 'to-agent', 'event', 'ready', 'loaded'])

const frame = ref(null)

const sandboxAttr = computed(() =>
  // never allow-same-origin: the doc stays in an opaque origin (no parent DOM access, no cookies)
  props.settings.allowScripts ? 'allow-scripts allow-popups allow-modals' : ''
)

/* ---- the host bridge injected into every rendered document --------------- */
// Closing-tag split so it survives being placed inside the document's HTML.
const CLOSE_SCRIPT = '<' + '/script>'
const PHIAL_SHIM =
  '<script>(function(){' +
  'if(window.phial)return;' +
  'function send(m){try{parent.postMessage(Object.assign({__phial:true},m),"*");}catch(e){}}' +
  'window.phial={' +
  'setState:function(d){send({type:"state",data:d});},' +
  'sendToAgent:function(t,d){send({type:"toAgent",text:String(t==null?"":t),data:d});},' +
  'emit:function(n,d){send({type:"event",name:String(n==null?"":n),data:d});},' +
  'ready:function(){send({type:"ready"});},' +
  'onData:function(cb){window.__phialOnData=cb;}' +
  '};' +
  'window.addEventListener("message",function(e){var d=e.data;if(d&&d.__phialHost&&d.type==="data"){' +
  'try{window.dispatchEvent(new CustomEvent("phial:data",{detail:d.data}));}catch(_){}' +
  'if(typeof window.__phialOnData==="function"){try{window.__phialOnData(d.data);}catch(_){}}}});' +
  '})();' + CLOSE_SCRIPT

function buildCsp() {
  const ext = props.settings.allowExternal
  const scripts = props.settings.allowScripts
  const httpsSrc = ext ? ' https:' : ''
  const directives = [
    "default-src 'none'",
    scripts ? `script-src 'unsafe-inline' 'unsafe-eval'${httpsSrc}` : null,
    `style-src 'unsafe-inline'${httpsSrc}`,
    `img-src data: blob:${httpsSrc}`,
    `font-src data:${httpsSrc}`,
    `media-src data: blob:${httpsSrc}`,
    "connect-src 'none'", // block fetch/XHR/websocket -> no data exfiltration
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'"
  ].filter(Boolean)
  return directives.join('; ')
}

function withInjections(rawHtml) {
  const head = `<meta http-equiv="Content-Security-Policy" content="${buildCsp()}">` +
    (props.settings.allowScripts ? PHIAL_SHIM : '')
  const src = rawHtml || '<!DOCTYPE html><html><head></head><body></body></html>'
  if (/<head[^>]*>/i.test(src)) {
    return src.replace(/<head[^>]*>/i, (m) => `${m}\n${head}`)
  }
  if (/<html[^>]*>/i.test(src)) {
    return src.replace(/<html[^>]*>/i, (m) => `${m}<head>${head}</head>`)
  }
  return `<!DOCTYPE html><html><head>${head}</head><body>${src}</body></html>`
}

function render() {
  if (frame.value) frame.value.srcdoc = withInjections(props.html)
}

function pushData(data) {
  try {
    frame.value?.contentWindow?.postMessage({ __phialHost: true, type: 'data', data }, '*')
  } catch (e) {
    /* ignore */
  }
}

function onFrameLoad() {
  emit('loaded')
  if (props.incomingData != null) pushData(props.incomingData)
}

function onMessage(e) {
  if (!frame.value || e.source !== frame.value.contentWindow) return
  const d = e.data
  if (!d || d.__phial !== true) return
  if (d.type === 'state') emit('state', d.data)
  else if (d.type === 'toAgent') emit('to-agent', { text: d.text, data: d.data })
  else if (d.type === 'event') emit('event', { name: d.name, data: d.data })
  else if (d.type === 'ready') emit('ready')
}

onMounted(() => {
  window.addEventListener('message', onMessage)
  render()
})
onBeforeUnmount(() => window.removeEventListener('message', onMessage))
watch(() => [props.html, props.settings.allowScripts, props.settings.allowExternal], render)
watch(() => props.incomingData, (v) => { if (v != null) pushData(v) })

defineExpose({ pushData })
</script>

<style scoped>
.sandbox-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
  display: block;
}
</style>
