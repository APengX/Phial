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
  incomingData: { default: null },
  // when true, the next click in the iframe captures the clicked element
  pickMode: { type: Boolean, default: false }
})
const emit = defineEmits(['state', 'to-agent', 'event', 'ready', 'loaded', 'pick', 'pick-cancel'])

const frame = ref(null)

const sandboxAttr = computed(() =>
  // never allow-same-origin: the doc stays in an opaque origin (no parent DOM access, no cookies)
  props.settings.allowScripts ? 'allow-scripts allow-popups allow-modals' : ''
)

/* ---- the host bridge injected into every rendered document --------------- */
// Closing-tag split so it survives being placed inside the document's HTML.
const CLOSE_SCRIPT = '<' + '/script>'
const PHIAL_SHIM_CORE = `(function(){
  if (window.phial) return;
  function send(m){ try { parent.postMessage(Object.assign({__phial:true},m),'*'); } catch(e){} }
  window.phial = {
    setState: function(d){ send({type:'state', data:d}); },
    sendToAgent: function(t,d){ send({type:'toAgent', text:String(t==null?'':t), data:d}); },
    emit: function(n,d){ send({type:'event', name:String(n==null?'':n), data:d}); },
    ready: function(){ send({type:'ready'}); },
    onData: function(cb){ window.__phialOnData = cb; }
  };
  window.addEventListener('message', function(e){
    var d = e.data;
    if (!d || !d.__phialHost) return;
    if (d.type === 'data') {
      try { window.dispatchEvent(new CustomEvent('phial:data', {detail: d.data})); } catch(_){}
      if (typeof window.__phialOnData === 'function') {
        try { window.__phialOnData(d.data); } catch(_){}
      }
    } else if (d.type === 'pickMode') {
      d.on ? _startPick() : _stopPick();
    }
  });

  // ---- element picker (host toggles via postMessage type:'pickMode') -------
  var _on = false, _hover = null, _prevOutline = '', _prevOffset = '', _prevCursor = '';
  function _startPick(){
    if (_on) return;
    _on = true;
    _prevCursor = document.body.style.cursor;
    document.body.style.cursor = 'crosshair';
    document.addEventListener('mouseover', _onHover, true);
    document.addEventListener('mouseout', _onUnhover, true);
    document.addEventListener('click', _onPick, true);
    document.addEventListener('keydown', _onKey, true);
  }
  function _stopPick(){
    if (!_on) return;
    _on = false;
    _unhighlight();
    document.body.style.cursor = _prevCursor;
    document.removeEventListener('mouseover', _onHover, true);
    document.removeEventListener('mouseout', _onUnhover, true);
    document.removeEventListener('click', _onPick, true);
    document.removeEventListener('keydown', _onKey, true);
  }
  function _highlight(el){
    if (_hover === el) return;
    _unhighlight();
    _hover = el;
    _prevOutline = el.style.outline;
    _prevOffset = el.style.outlineOffset;
    el.style.outline = '2px solid #6d28d9';
    el.style.outlineOffset = '1px';
  }
  function _unhighlight(){
    if (!_hover) return;
    _hover.style.outline = _prevOutline;
    _hover.style.outlineOffset = _prevOffset;
    _hover = null;
  }
  function _onHover(e){
    var t = e.target;
    if (t && t.nodeType === 1 && t !== document.body && t !== document.documentElement) _highlight(t);
  }
  function _onUnhover(e){ if (e.target === _hover) _unhighlight(); }
  function _onPick(e){
    e.preventDefault();
    e.stopImmediatePropagation();
    var el = e.target;
    var info = _describe(el);
    _stopPick();
    send({type:'pick', data: info});
  }
  function _onKey(e){
    if (e.key === 'Escape') { _stopPick(); send({type:'pickCancel'}); }
  }
  function _describe(el){
    var classes = (typeof el.className === 'string') ? el.className.trim() : '';
    var html = el.outerHTML || '';
    var truncated = html.length > 4000;
    return {
      tagName: el.tagName,
      id: el.id || '',
      classes: classes,
      text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 200),
      outerHTML: truncated ? html.slice(0, 4000) + '[...truncated]' : html,
      truncated: truncated,
      selector: _selector(el)
    };
  }
  function _selector(el){
    var parts = [], cur = el, depth = 0;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 6) {
      var part = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift(part + '#' + cur.id); break; }
      if (typeof cur.className === 'string' && cur.className.trim()) {
        var cls = cur.className.trim().split(/\\s+/).slice(0,2).join('.');
        if (cls) part += '.' + cls;
      }
      var p = cur.parentNode;
      if (p && p.children) {
        var sibs = [];
        for (var i = 0; i < p.children.length; i++) {
          if (p.children[i].tagName === cur.tagName) sibs.push(p.children[i]);
        }
        if (sibs.length > 1) part += ':nth-of-type(' + (sibs.indexOf(cur) + 1) + ')';
      }
      parts.unshift(part);
      cur = cur.parentNode;
      depth++;
    }
    return parts.join(' > ');
  }
})();`
const PHIAL_SHIM = '<script>' + PHIAL_SHIM_CORE + CLOSE_SCRIPT

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
  // re-arm pick mode after a re-render if the host still wants it on
  if (props.pickMode) sendPickMode(true)
}

function onMessage(e) {
  if (!frame.value || e.source !== frame.value.contentWindow) return
  const d = e.data
  if (!d || d.__phial !== true) return
  if (d.type === 'state') emit('state', d.data)
  else if (d.type === 'toAgent') emit('to-agent', { text: d.text, data: d.data })
  else if (d.type === 'event') emit('event', { name: d.name, data: d.data })
  else if (d.type === 'ready') emit('ready')
  else if (d.type === 'pick') emit('pick', d.data)
  else if (d.type === 'pickCancel') emit('pick-cancel')
}

function sendPickMode(on) {
  try {
    frame.value?.contentWindow?.postMessage({ __phialHost: true, type: 'pickMode', on: !!on }, '*')
  } catch (e) {
    /* ignore */
  }
}

onMounted(() => {
  window.addEventListener('message', onMessage)
  render()
})
onBeforeUnmount(() => window.removeEventListener('message', onMessage))
watch(() => [props.html, props.settings.allowScripts, props.settings.allowExternal], render)
watch(() => props.incomingData, (v) => { if (v != null) pushData(v) })
watch(() => props.pickMode, sendPickMode)

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
