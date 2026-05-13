<template>
  <NodeViewWrapper
    class="phial-widget"
    :class="{ selected: selected }"
    data-drag-handle
  >
    <!-- Sandbox iframe: same security envelope as SandboxPreview (allow-
         scripts, NEVER allow-same-origin; CSP injected via <meta>). This is
         a *preview*, not the full window.phial bridge — that loop runs in
         the main Preview / Split view. Users who want to interact end-to-end
         (state → AI) should use those modes. -->
    <iframe
      ref="iframeEl"
      class="pw-frame"
      sandbox="allow-scripts"
      :srcdoc="srcdoc"
      :title="t('blocks.widget.frameTitle')"
    />

    <!-- Toolbar sits on top of the frame, fading in on hover/selection. Edit
         opens the host-provided modal (BlockEditor.vue) which writes the new
         HTML back via updateAttributes. -->
    <div class="pw-toolbar">
      <span class="pw-badge" :title="t('blocks.widget.badge')">{{ t('blocks.widget.badge') }}</span>
      <span class="pw-spacer"></span>
      <button
        type="button"
        class="pw-btn"
        :title="t('blocks.widget.edit')"
        @click="requestEdit"
      >✎ {{ t('blocks.widget.edit') }}</button>
    </div>
  </NodeViewWrapper>
</template>

<script setup>
// NodeView for the PhialWidget node. Receives the standard TipTap-Vue props
// (node, updateAttributes, editor, selected, …) — see
// https://tiptap.dev/docs/editor/api/node-views/vue.
//
// The iframe is rebuilt from scratch whenever the widget's HTML changes
// (which only happens via the edit modal — atom nodes don't accept inline
// edits). We don't postMessage state in/out: the in-editor preview is
// intentionally one-way. The host's main Preview/Split view is where the
// window.phial bridge actually runs.

import { computed } from 'vue'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'

const props = defineProps(nodeViewProps)
const { t } = useI18n()

const srcdoc = computed(() => wrapForSandbox(props.node.attrs.html || ''))

function wrapForSandbox(html) {
  // Tight CSP: allow inline scripts/styles within the sandbox (the widget
  // itself), but block any network calls so a misbehaving widget can't phone
  // home from the editor preview. Anything that needs CDN works in the main
  // SandboxPreview (which honors the user's CDN toggle).
  const csp = [
    "default-src 'none'",
    "script-src 'unsafe-inline'",
    "style-src 'unsafe-inline'",
    "img-src data: blob:",
    "font-src data:",
    "connect-src 'none'",
  ].join('; ')
  return `<!doctype html><html><head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<style>
  html,body { margin: 0; padding: 0; }
  body { padding: 12px; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2328; }
</style>
</head><body>${html}</body></html>`
}

function requestEdit() {
  const fn = props.extension?.options?.onEditRequest
  if (typeof fn !== 'function') return
  fn({
    html: props.node.attrs.html || '',
    update: (newHtml) => props.updateAttributes({ html: newHtml }),
  })
}
</script>

<style scoped>
.phial-widget {
  position: relative;
  margin: 12px 0;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  transition: border-color .12s ease, box-shadow .12s ease;
}
.phial-widget:hover {
  border-color: #c8cbd1;
}
.phial-widget.selected {
  border-color: var(--accent, #6d28d9);
  box-shadow: 0 0 0 2px var(--accent-soft, #ede9fe);
}

.pw-frame {
  display: block;
  width: 100%;
  height: 320px;
  border: 0;
  background: #fff;
}

.pw-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 4px 10px;
  font-size: 12px;
  background: var(--bg-panel, #fafbfc);
  border-top: 1px solid var(--border, #e4e6eb);
  color: var(--text-dim, #6b7280);
}
.pw-spacer { flex: 1; }
.pw-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: .04em;
  background: var(--accent-soft, #ede9fe);
  color: var(--accent, #6d28d9);
  border-radius: 999px;
  font-weight: 500;
}
.pw-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  font-size: 12px;
  background: #fff;
  border: 1px solid var(--border, #e4e6eb);
  border-radius: 5px;
  cursor: pointer;
  color: inherit;
}
.pw-btn:hover { background: var(--accent-soft, #f3f4f6); border-color: #c8cbd1; }
</style>
