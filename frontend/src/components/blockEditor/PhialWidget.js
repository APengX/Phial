// Custom TipTap node that represents one "interactive widget" inside the
// document — an opaque blob of HTML (typically containing <script>) that the
// block editor renders inside a sandboxed mini-iframe via PhialWidgetView.
//
// On the wire (i.e. in TipTap's getHTML output) a widget shows up as
//   <div data-phial-widget="true" data-html="<urlencoded raw HTML>"></div>
// The host (BlockEditor.vue) post-processes that with `unwrapWidgets` before
// emitting the save value, so the placeholder never appears in the on-disk
// .html. Parsing is symmetric: `splitProseAndWidgets` produces the same
// placeholder shape, which `parseHTML` below recognises.

import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import PhialWidgetView from './PhialWidgetView.vue'

export const PhialWidget = Node.create({
  name: 'phialWidget',
  group: 'block',
  // Atom: no editable content inside. Selectable & draggable so the existing
  // drag handle / Backspace / arrow navigation all behave like for any other
  // block.
  atom: true,
  selectable: true,
  draggable: true,
  defining: true,

  addOptions() {
    return {
      // Called by the NodeView when the user clicks "Edit HTML". Wired up by
      // BlockEditor.vue to open the WidgetEditModal and write the new HTML
      // back via the supplied `update(html)` callback.
      onEditRequest: null,
    }
  },

  addAttributes() {
    return {
      html: {
        default: '',
        parseHTML: (el) => {
          const raw = el.getAttribute('data-html') || ''
          try { return decodeURIComponent(raw) } catch { return raw }
        },
        renderHTML: (attrs) => ({
          'data-html': encodeURIComponent(attrs.html || ''),
        }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-phial-widget]' }]
  },

  renderHTML({ HTMLAttributes }) {
    // Empty content (`[]`) — atom nodes have no body. Merge `data-html` from
    // addAttributes with the marker attr the parser keys off.
    return ['div', mergeAttributes(HTMLAttributes, { 'data-phial-widget': 'true' }), []]
  },

  addNodeView() {
    return VueNodeViewRenderer(PhialWidgetView)
  },
})

export default PhialWidget
