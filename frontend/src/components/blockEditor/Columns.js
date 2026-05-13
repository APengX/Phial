// Multi-column layout block. Two nested nodes:
//
//   columns: outer container, marked `<div data-phial-columns>` so the doc
//            parser knows this isn't a widget. Holds 2–4 column children.
//   column:  one column, marked `<div data-phial-column>`, holds blocks.
//
// PR 4 ships static layouts (2 or 3 columns chosen at insertion). PR 5 will
// add column-count adjustment + drag blocks between columns.

import { Node, mergeAttributes } from '@tiptap/core'

export const Columns = Node.create({
  name: 'columns',
  group: 'block',
  // 2–4 columns. ProseMirror enforces this on insert/delete so the user
  // can't accidentally end up with a single-column "columns" block (which
  // would defeat the point).
  content: 'column{2,4}',
  defining: true,
  isolating: true,

  parseHTML() {
    return [{ tag: 'div[data-phial-columns]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, {
        'data-phial-columns': 'true',
        class: 'phial-columns',
      }),
      0,
    ]
  },
})

export const Column = Node.create({
  name: 'column',
  // One column holds standard block content. Not isolating so arrow keys
  // can move the cursor between adjacent columns — the outer `columns`
  // wrapper handles drag/structure isolation.
  content: 'block+',
  defining: true,

  parseHTML() {
    return [{ tag: 'div[data-phial-column]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, {
        'data-phial-column': 'true',
        class: 'phial-column',
      }),
      0,
    ]
  },
})

export default Columns
