// Bundled interactive example documents. The HTML lives under public/examples/
// so it's just a static file; HomeView fetches it and creates a workspace doc.
export const EXAMPLES = [
  {
    id: 'priority-board',
    file: '/examples/priority-board.html',
    defaultPath: '示例-优先级看板.html',
    title: { zh: '优先级看板（可拖拽）', en: 'Priority board (drag & drop)' },
    desc: {
      zh: '把 ticket 拖进 Now / Next / Later / Cut 四列、列内排序，一键导出 Markdown 并回传给 AI —— 演示 phial.setState / phial.sendToAgent。',
      en: 'Drag tickets across Now / Next / Later / Cut, reorder within a column, export Markdown back to the AI — demonstrates phial.setState / phial.sendToAgent.'
    }
  },
  {
    id: 'prompt-lab',
    file: '/examples/prompt-lab.html',
    defaultPath: '示例-Prompt工作台.html',
    title: { zh: 'Prompt 工作台', en: 'Prompt lab' },
    desc: {
      zh: '左边编辑 system prompt，右边样例输入 + 实时拼接预览，底部 token 粗估，应用后把 prompt 回传 AI。',
      en: 'Edit a system prompt, sample input with a live assembled preview, rough token count, then apply it back to the AI.'
    }
  }
]
