// Collapsible "toggle" block — maps cleanly to native HTML `<details>` +
// `<summary>`. No JS required at render time, no special markup; opens in
// any browser. Two nodes:
//   - toggle:        the container (`<details>`); holds [summary, ...block+]
//   - toggleSummary: the clickable header (`<summary>`), inline content
//
// In the editor we always render `<details open>` so the writer sees the
// content while typing. The saved HTML carries the `open` attr — readers
// who want a collapsed default can remove it from source view; PR 5 will
// add a NodeView toggle button so authors can pick the saved state per
// block without leaving Blocks mode.

import { Node, mergeAttributes } from '@tiptap/core'

export const Toggle = Node.create({
  name: 'toggle',
  group: 'block',
  content: 'toggleSummary block+',
  defining: true,

  parseHTML() {
    return [{ tag: 'details' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['details', mergeAttributes(HTMLAttributes, { open: 'open' }), 0]
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
