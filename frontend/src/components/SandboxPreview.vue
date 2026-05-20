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
  pickMode: { type: Boolean, default: false },
  // when true, clicking elements in the iframe allows editing their text content
  editMode: { type: Boolean, default: false }
})
const emit = defineEmits(['state', 'to-agent', 'event', 'ready', 'loaded', 'pick', 'pick-cancel', 'edit', 'edit-cancel', 'navigate'])

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
  document.addEventListener('click', function(e){
    var t = e.target;
    if (!t || !t.closest) return;
    // internal workspace-doc links: open via the host app, never in the iframe
    var doc = t.closest('a[data-phial-doc]');
    if (doc) {
      e.preventDefault();
      send({type:'navigate', href: doc.getAttribute('data-phial-doc')});
      return;
    }
    // in-page anchors: scroll here. A bare '#id' link in a srcdoc iframe would
    // otherwise resolve against the *parent* URL and navigate the iframe away.
    var frag = t.closest('a[href^="#"]');
    if (frag) {
      e.preventDefault();
      var id = '';
      try { id = decodeURIComponent(frag.getAttribute('href').slice(1)); }
      catch(_) { id = frag.getAttribute('href').slice(1); }
      var el = id ? document.getElementById(id) : null;
      if (el) el.scrollIntoView({behavior:'smooth', block:'start'});
      else window.scrollTo({top:0, behavior:'smooth'});
    }
  }, true);

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
    } else if (d.type === 'editMode') {
      d.on ? _startEdit() : _stopEdit();
    } else if (d.type === 'scrollTo') {
      try {
        var hs = document.querySelectorAll('h1,h2,h3');
        var tgt = hs[d.index];
        if (tgt) tgt.scrollIntoView({behavior:'smooth', block:'start'});
      } catch(_){}
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
    el.style.outline = '2px solid #d97757';
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

  // ---- edit mode (host toggles via postMessage type:'editMode') ------------
  var _editOn = false, _editHover = null, _editPrevOutline = '', _editPrevOffset = '';
  function _startEdit(){
    if (_editOn) return;
    _editOn = true;
    document.body.style.cursor = 'text';
    document.addEventListener('mouseover', _onEditHover, true);
    document.addEventListener('mouseout', _onEditUnhover, true);
    document.addEventListener('click', _onEditClick, true);
    document.addEventListener('keydown', _onEditKey, true);
  }
  function _stopEdit(){
    if (!_editOn) return;
    _editOn = false;
    _editUnhighlight();
    document.body.style.cursor = '';
    document.removeEventListener('mouseover', _onEditHover, true);
    document.removeEventListener('mouseout', _onEditUnhover, true);
    document.removeEventListener('click', _onEditClick, true);
    document.removeEventListener('keydown', _onEditKey, true);
  }
  function _editHighlight(el){
    if (_editHover === el) return;
    _editUnhighlight();
    _editHover = el;
    _editPrevOutline = el.style.outline;
    _editPrevOffset = el.style.outlineOffset;
    el.style.outline = '2px dashed #788c5d';
    el.style.outlineOffset = '1px';
  }
  function _editUnhighlight(){
    if (!_editHover) return;
    _editHover.style.outline = _editPrevOutline;
    _editHover.style.outlineOffset = _editPrevOffset;
    _editHover = null;
  }
  function _onEditHover(e){
    var t = e.target;
    if (t && t.nodeType === 1 && t !== document.body && t !== document.documentElement) _editHighlight(t);
  }
  function _onEditUnhover(e){ if (e.target === _editHover) _editUnhighlight(); }
  function _onEditClick(e){
    e.preventDefault();
    e.stopImmediatePropagation();
    var el = e.target;
    var text = _getEditableText(el);
    var selector = _selector(el);
    _editUnhighlight();
    send({type:'edit', data: { selector: selector, text: text, tagName: el.tagName }});
  }
  function _onEditKey(e){
    if (e.key === 'Escape') { _stopEdit(); send({type:'editCancel'}); }
  }
  function _getEditableText(el){
    // Get direct text content, excluding nested elements
    var text = '';
    for (var i = 0; i < el.childNodes.length; i++) {
      var node = el.childNodes[i];
      if (node.nodeType === 3) text += node.nodeValue;
    }
    return text.trim();
  }
})();`
const PHIAL_SHIM = '<script>' + PHIAL_SHIM_CORE + CLOSE_SCRIPT
const DOC_LINK_STYLE = '<style>a[data-phial-doc]{cursor:pointer}</style>'

/* Internal workspace-doc links (relative *.html, or `?path=` refs) would
   otherwise navigate the sandboxed iframe itself — resolved against the app
   origin, that lands on a blank page. Strip the href into data-phial-doc so
   the shim can turn a click into a host-side 'navigate' instead. */
function isInternalDocHref(href) {
  const h = (href || '').trim()
  if (!h || /^(https?:|mailto:|tel:|javascript:|data:|#)/i.test(h)) return false
  if (/[?&]path=/.test(h)) return true
  return /\.html?$/i.test(h.split(/[?#]/)[0])
}

function neutralizeDocLinks(html) {
  return html.replace(/<a\b[^>]*>/gi, (tag) => {
    const m = tag.match(/\bhref\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+)/i)
    if (!m) return tag
    let val = m[1]
    if (val[0] === '"' || val[0] === "'") val = val.slice(1, -1)
    if (!isInternalDocHref(val)) return tag
    return tag.replace(m[0], `data-phial-doc="${val.replace(/"/g, '&quot;')}"`)
  })
}

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
  // Pin the base URL to about:srcdoc so relative links / `#fragment` anchors
  // resolve within the iframe instead of against the parent app URL — without
  // this, a bare `#id` link navigates the iframe away to a blank page.
  const head = '<base href="about:srcdoc">' +
    `<meta http-equiv="Content-Security-Policy" content="${buildCsp()}">` +
    (props.settings.allowScripts ? PHIAL_SHIM + DOC_LINK_STYLE : '')
  const src = neutralizeDocLinks(rawHtml || '<!DOCTYPE html><html><head></head><body></body></html>')
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
  // re-arm edit mode after a re-render if the host still wants it on
  if (props.editMode) sendEditMode(true)
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
  else if (d.type === 'edit') emit('edit', d.data)
  else if (d.type === 'editCancel') emit('edit-cancel')
  else if (d.type === 'navigate') emit('navigate', d.href)
}

function sendPickMode(on) {
  try {
    frame.value?.contentWindow?.postMessage({ __phialHost: true, type: 'pickMode', on: !!on }, '*')
  } catch (e) {
    /* ignore */
  }
}

function sendEditMode(on) {
  try {
    frame.value?.contentWindow?.postMessage({ __phialHost: true, type: 'editMode', on: !!on }, '*')
  } catch (e) {
    /* ignore */
  }
}

// Scroll the rendered doc to its Nth heading (h1/h2/h3, document order) — the
// outline panel uses this. No-op when in-doc JS is off (the shim isn't there).
function scrollToHeading(index) {
  try {
    frame.value?.contentWindow?.postMessage(
      { __phialHost: true, type: 'scrollTo', index },
      '*'
    )
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
watch(() => props.editMode, sendEditMode)

defineExpose({ pushData, scrollToHeading })
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
