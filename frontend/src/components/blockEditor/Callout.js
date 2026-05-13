// "Callout" block — a sidebar-style box with an icon + body. Maps to
// `<aside class="phial-callout" data-icon="…">…</aside>` so the saved HTML
// renders nicely in any browser (semantic, no JS).
//
// The icon is a single attribute (emoji by default); CalloutView gives the
// author a small picker so they can pick a different one without leaving
// Blocks mode.

import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import CalloutView from './CalloutView.vue'

const DEFAULT_ICON = '💡'

export const Callout = Node.create({
  name: 'callout',
  group: 'block',
  content: 'block+',
  defining: true,

  addAttributes() {
    return {
      icon: {
        default: DEFAULT_ICON,
        parseHTML: (el) => el.getAttribute('data-icon') || DEFAULT_ICON,
        renderHTML: (attrs) => ({ 'data-icon': attrs.icon || DEFAULT_ICON }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'aside.phial-callout' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'aside',
      mergeAttributes(HTMLAttributes, { class: 'phial-callout' }),
      0,
    ]
  },

  addNodeView() {
    return VueNodeViewRenderer(CalloutView)
  },
})

export default Callout
