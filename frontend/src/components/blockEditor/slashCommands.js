// Slash-command TipTap extension: types `/` to open a filterable menu of
// block types (Notion-style). The extension itself is a thin wrapper around
// `@tiptap/suggestion`; the actual menu UI is a Vue component (SlashMenuList)
// mounted/positioned by the consumer (BlockEditor.vue) via the render hooks
// passed in through options.suggestion.

import { Extension } from '@tiptap/core'
import Suggestion from '@tiptap/suggestion'

export const SlashCommands = Extension.create({
  name: 'slashCommands',

  addOptions() {
    return {
      suggestion: {
        char: '/',
        // The suggestion utility removes the trigger character + query from
        // the doc before calling our command; we just run the chosen action.
        command: ({ editor, range, props }) => {
          props.command({ editor, range })
        },
        // `allowSpaces: false` — once the user types a space the menu closes
        // (matches Notion). `startOfLine: false` — `/` works mid-block too.
        allowSpaces: false,
        startOfLine: false,
      },
    }
  },

  addProseMirrorPlugins() {
    return [
      Suggestion({
        editor: this.editor,
        ...this.options.suggestion,
      }),
    ]
  },
})

export default SlashCommands
