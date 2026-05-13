// Collapsible "toggle" block — maps cleanly to native HTML `<details>` +
// `<summary>`. No JS required at render time, no special markup; opens in
// any browser. Two nodes:
//   - toggle:        the container (`<details>`); holds [summary, ...block+]
//   - toggleSummary: the clickable header (`<summary>`), inline content
//
// `open` attribute (PR 5): captures the SAVED default — i.e. whether the
// reader sees the body expanded on first view. The editor always shows the
// body (ToggleView forces open=true on its rendered <details>), regardless.
// ToggleView gives authors a chevron control to flip this attr in-place.

import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import ToggleView from './ToggleView.vue'

export const Toggle = Node.create({
  name: 'toggle',
  group: 'block',
  content: 'toggleSummary block+',
  defining: true,

  addAttributes() {
    return {
      open: {
        default: true,
        parseHTML: (el) => el.hasAttribute('open'),
        // Only emit `open` when true — the saved HTML stays minimal for the
        // common "open by default" case and switches to bare <details> when
        // the author has explicitly chosen a closed-by-default state.
        renderHTML: (attrs) => (attrs.open ? { open: 'open' } : {}),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'details' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['details', mergeAttributes(HTMLAttributes), 0]
  },

  addNodeView() {
    return VueNodeViewRenderer(ToggleView)
  },
})

export const ToggleSummary = Node.create({
  name: 'toggleSummary',
  // Inline-only content. Listing matters: must come before generic block
  // content in the parent `toggle` node's content spec.
  content: 'inline*',
  // Deliberately NOT isolating: the user expects arrow-down from the
  // summary line to drop into the toggle body. `defining` is enough to
  // keep the slot stable across content edits.
  defining: true,

  parseHTML() {
    return [{ tag: 'summary' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['summary', mergeAttributes(HTMLAttributes, {}), 0]
  },
})

export default Toggle
