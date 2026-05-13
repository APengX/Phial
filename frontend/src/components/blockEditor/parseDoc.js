// Parses a Phial document body for the block editor:
//
//   splitProseAndWidgets(bodyHtml) → editor-input HTML where each non-prose
//     region is collapsed into a `<div data-phial-widget data-html="…">`
//     placeholder that the PhialWidget TipTap node parses back.
//
//   unwrapWidgets(htmlFromTiptap) → save-shape HTML where every placeholder
//     div is replaced with its original raw markup. Round-trip is identity
//     for the widget portions (TipTap never touches their bytes).
//
// The split rule is intentionally coarse: any top-level element that's *not*
// in the prose schema (or any prose element that contains a <script>) starts
// a widget run, and consecutive widget elements coalesce. This keeps an AI-
// generated widget (`<div id="kanban">…</div>` + `<script>…</script>`) as one
// block, surrounded by editable prose, while leaving plain `<p>` / `<h1>`
// markup alone.

const PROSE_TAGS = new Set([
  'P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
  'UL', 'OL', 'BLOCKQUOTE', 'PRE', 'HR',
  'FIGURE', 'IMG',
  // PR 4 schema additions — TipTap can parse these into proper block nodes,
  // so they should ride through as prose instead of being collapsed into a
  // widget block.
  'TABLE', 'DETAILS',
])

const PLACEHOLDER_TAG = 'div'

// One place to ask "can TipTap render this top-level element?". A few shapes
// (notably the column container) carry a `data-phial-*` marker that the
// custom nodes' parseHTML rules key off — we mirror that check here so the
// splitter doesn't swallow them into a widget.
function isProseShape(el) {
  const tag = el.tagName
  if (PROSE_TAGS.has(tag)) return true
  if (tag === 'DIV' && el.hasAttribute('data-phial-columns')) return true
  return false
}

export function splitProseAndWidgets(bodyHtml) {
  if (!bodyHtml || !bodyHtml.trim()) return ''
  const tmpl = document.createElement('template')
  tmpl.innerHTML = bodyHtml

  const parts = []
  let widgetBuf = ''

  const flushWidget = () => {
    if (!widgetBuf) return
    parts.push(makePlaceholder(widgetBuf))
    widgetBuf = ''
  }

  for (const node of Array.from(tmpl.content.childNodes)) {
    // Element nodes
    if (node.nodeType === 1) {
      const tag = node.tagName
      const html = node.outerHTML
      // Anything carrying / containing a <script> is widget regardless of
      // shape — a `<details>` with embedded JS still can't be safely round-
      // tripped through the prose editor.
      const hasScript = tag === 'SCRIPT' || node.querySelector?.('script') != null
      const isProse = isProseShape(node) && !hasScript
      if (isProse) {
        flushWidget()
        parts.push(html)
      } else {
        widgetBuf += html
      }
      continue
    }
    // Text nodes — preserve non-whitespace as prose paragraphs; collapse
    // whitespace runs (the body between two block elements). Comments and
    // anything else: drop.
    if (node.nodeType === 3) {
      const t = node.textContent
      if (t.trim()) {
        flushWidget()
        parts.push(`<p>${escapeHtml(t)}</p>`)
      }
    }
  }
  flushWidget()

  return parts.join('\n')
}

export function unwrapWidgets(htmlFromTiptap) {
  if (!htmlFromTiptap) return htmlFromTiptap
  if (!htmlFromTiptap.includes('data-phial-widget')) return htmlFromTiptap
  const tmpl = document.createElement('template')
  tmpl.innerHTML = htmlFromTiptap
  // querySelectorAll is live-free against a DocumentFragment, but we read
  // into an array up-front anyway so replaceWith() doesn't shift indices.
  const placeholders = Array.from(
    tmpl.content.querySelectorAll(`${PLACEHOLDER_TAG}[data-phial-widget]`)
  )
  for (const el of placeholders) {
    const encoded = el.getAttribute('data-html') || ''
    let original = ''
    try { original = decodeURIComponent(encoded) } catch { original = encoded }
    if (!original) {
      el.remove()
      continue
    }
    const wrap = document.createElement('template')
    wrap.innerHTML = original
    el.replaceWith(...wrap.content.childNodes)
  }
  return tmpl.innerHTML
}

// ---- internals ------------------------------------------------------------

function makePlaceholder(html) {
  return `<${PLACEHOLDER_TAG} data-phial-widget="true" data-html="${encodeURIComponent(html)}"></${PLACEHOLDER_TAG}>`
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
