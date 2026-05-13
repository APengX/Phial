<div align="center">

<img src="frontend/public/icon.svg" alt="Phial" width="88" height="88" />

# Phial

**HTML-native document manager — write with AI agents, read rich interactive docs.**

<sub>取自《指环王》中加拉德瑞尔的水晶瓶（Phial of Galadriel）—— *"愿它在你前路无光时，为你照亮黑暗。"*</sub>

中文 · [English below](#english)

</div>

---

## 这是什么

Phial 是一个开源的文档管理工具，定位类似 Typora / Obsidian，但**文档的原生格式是 HTML 而不是 Markdown** —— 而且它要的不是「Markdown 套层 CSS 的假可视化」，是真的把 HTML 当**可操作的界面**来用：

- **内容以 HTML 形式展示与存储** —— 一个文档就是一个 `.html` 文件，可移植、任何浏览器都能打开、零锁定。
- **AI agent 生成的不止是「给你看的文档」，而是「你能操作的界面」** —— 内置聊天面板，描述需求，模型直接产出 HTML，Phial 自动渲染；如果需求涉及拖动 / 排序 / 筛选 / 调参 / 对比，它会给你一个真能用的看板 / 调参台，而不是一段排好版的文字。
- **操作结果能回传给 AI，形成闭环** —— 渲染出来的文档可以通过注入的 `window.phial` 桥把当前状态（重排后的看板、改好的 prompt……）发回对话，AI 接着这一步继续。

> 这也是 HTML 相比 Markdown 的核心差异：它不只承载文字，还承载布局、图示、交互和视觉层级。
> 人在做判断时，往往不是线性阅读，而是在比较、移动、筛选、调整、反复看效果 —— HTML 把这些动作接住了。
>
> 例：要给 30 个 Linear ticket 排优先级，在聊天框里一条条说「这个往前、那个往后」很别扭；让 AI 直接生成一个有 Now/Next/Later/Cut 四列、卡片可拖拽的 HTML 看板，你拖完一键导出 Markdown 回传，自然得多。调 system prompt 同理：左边可编辑 prompt、右边样例输入和实时预览、底部 token 计数和复制按钮。

## 架构

```
Phial/
├── package.json          # 根脚本：concurrently 一键起前后端
├── .env.example
├── backend/              # Flask 应用工厂 + 蓝图，uv 管依赖
│   ├── run.py
│   └── app/
│       ├── __init__.py   # create_app()
│       ├── config.py     # 从 .env 读配置
│       ├── api/          # /api/documents, /api/workspace, /api/agents, /api/ai
│       ├── services/     # workspace, app_settings, llm_client, html_agent, agents, cli_agent
│       └── utils/
└── frontend/             # Vue 3 + Vite + vue-router + vue-i18n + axios + CodeMirror
    └── src/
        ├── views/        # HomeView（工作区/文档列表/示例）、EditorView（三栏）
        ├── components/   # FileTree / HtmlEditor / SandboxPreview / AiPanel / SettingsModal
        └── api/
```

- **后端**：Flask（app factory，蓝图挂 `/api/*`），`services/` 业务层；Python ≥ 3.11（实际跑 3.12），`uv` 管依赖。
- **前端**：Vue 3 + Vite，`/api` 代理到后端 `:5001`；HTML 源码用 CodeMirror 编辑。
- **生成 HTML 的 agent —— 可选**（设置里切换，详见下文「选择 agent」）：
  - **内置 LLM API**：OpenAI 兼容格式（`openai` SDK），配 `.env` 里的 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`；
  - **本地 CLI agent**：检测到 `claude`（Claude Code）/ `codex` / `gemini` 就能选，Phial 在工作区目录里以非交互模式调用它，拿回它输出的 HTML。
- **渲染沙箱**：渲染交给 `<iframe sandbox="allow-scripts">`（绝不给 `allow-same-origin`）+ 注入 CSP；默认允许文档内 JS 跑（动画/图表/交互），默认禁止联网（`connect-src 'none'`），可在设置里放开外部资源（CDN）。
- **文档存储**：本地工作区文件夹，一个文档 = 一个 `.html` 文件，可用 git 直接管理。
- **配置存储**：工作区路径 / 渲染开关 / 选用的 agent + 模型 + 环境变量，统一存在 `~/.phial/settings.json`。

## `window.phial` —— 文档 ↔ AI 的回传桥

Phial 渲染每个文档时会往它的 `<head>` 注入一小段脚本，给文档里的 JS 提供一个全局 `phial` 对象（启用「JS」开关时可用）：

| 方法 | 作用 |
|------|------|
| `phial.setState(obj)` | 上报「当前界面状态」（重排后的看板、用户的勾选、编辑后的 prompt……）。每次用户操作改变状态就调它；这个状态会作为上下文自动附在你下一条 AI 消息里。 |
| `phial.sendToAgent(text, obj?)` | 一键把结果回传给 AI 并触发新一轮对话。接到界面里的主按钮上，比如「确认排序」「导出 Markdown 并发回」「应用这个 prompt」。 |
| `phial.emit(name, data?)` | 发一个一次性事件给宿主（轻量通知）。 |
| `phial.ready()` / `phial.onData(cb)` | 可选：初始化完成 / 接收宿主传入的数据。 |

写文档的 AI 知道这套 API（系统提示里有说明），所以你说「给这些 ticket 排个优先级」时它会生成带拖拽 + `phial.setState` + 导出按钮的看板。首页的「示例」里有两个现成的可玩：**优先级看板（可拖拽）** 和 **Prompt 工作台**。

## 选择 agent

右上角 ⚙ 打开设置。Phial 启动时会扫 PATH，看本地装没装 `claude` / `codex` / `gemini`，列出来给你选：

- **内置 LLM API** —— 用 `.env` 里配的 OpenAI 兼容接口（默认）。
- **某个 CLI agent** —— 选它之后可以单独填 **model** 和一组 **环境变量**（会注入到调用该 CLI 的子进程里，比如 `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`、`OPENAI_API_KEY`……每个 agent 设置面板里给了建议项）。Phial 会在工作区目录里以非交互模式调用它（`claude -p` / `codex exec` / `gemini -p`），把它打印出来的 HTML 抽出来渲染。`codex` / `gemini` 的支持是尽力而为，`claude` 调得最稳。

不管选哪个，文档侧的 `window.phial` 回传闭环都一样工作。

## 快速开始

### 前置依赖

| 工具 | 版本 | 检查 |
|------|------|------|
| Node.js | 18+ | `node -v` |
| Python | ≥ 3.11 | `python --version` |
| uv | latest | `uv --version` |

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等
```

### 2. 安装依赖

```bash
npm run setup:all      # 根 + frontend (npm) + backend (uv)
```

### 3. 启动

```bash
npm run dev            # 同时起后端(:5001) 和前端(:3000)
```

- 前端：http://localhost:3000
- 后端 API：http://localhost:5001

单独启动：`npm run backend` / `npm run frontend`

## 路线图

- [x] 本地工作区 + `.html` 文档 CRUD
- [x] 三栏编辑器：文件树 / HTML 源码编辑 / 实时沙箱预览
- [x] AI 面板：聊天 → 流式生成 HTML / 界面 → 自动渲染
- [x] `window.phial` 回传桥（`setState` / `sendToAgent`）+ 交互示例文档
- [x] 可插拔 agent：内置 LLM API / 本地 CLI（Claude Code、Codex、Gemini）+ 设置面板（检测、选 agent、配模型与环境变量）
- [x] 按文档绑定的代码 / 笔记文件夹做对话上下文（首页给每个 `.html` 挂本地目录，对话时按字符上限自动塞进 prompt）
- [ ] CLI agent 流式更细粒度（解析 `claude --output-format stream-json`）、让它直接改文件
- [ ] 文档全文搜索、标签
- [ ] 更多内置模板（日程规划、方案对比、清单分类、表单……）
- [ ] 暴露 MCP server，让外部 agent（Claude Code / Cursor）直接驱动
- [ ] 导出（单文件 HTML / PDF / Markdown）、版本历史
- [ ] 可视化块编辑（类 Notion）

## 协议

MIT（暂定，可调整）。

---

<a name="english"></a>
## English

**Phial** is an open-source document manager — think Typora / Obsidian, but the native format is **HTML instead of Markdown**, and it treats HTML as an *operable interface*, not "Markdown with a coat of CSS":

- **Content is stored & displayed as HTML** — one document = one `.html` file. Portable, opens in any browser, zero lock-in.
- **The AI generates interfaces, not just documents** — built-in chat panel; if your request involves dragging / ranking / filtering / tuning / comparing, you get a working board or tuner you can manipulate, not a tidy write-up.
- **Your actions flow back to the AI** — rendered docs use an injected `window.phial` bridge (`setState`, `sendToAgent`) to send their current state (a reordered board, an edited prompt…) back into the conversation so the AI can continue from there.

Rendering happens inside a sandboxed iframe (`allow-scripts`, never `allow-same-origin`, plus an injected CSP) — in-document JS runs, but network access is blocked by default. Two interactive examples ship on the home screen: a draggable **priority board** and a **prompt lab**.

**Pluggable agents**: in Settings (⚙) you can use the built-in OpenAI-compatible client (configured in `.env`) or, if Phial detects them on your PATH, a local CLI agent — `claude` (Claude Code), `codex`, or `gemini` — with its own model and environment variables. Phial invokes the CLI non-interactively in the workspace folder and extracts the HTML it prints.

Stack: Flask backend (app-factory + blueprints, `uv`) + Vue 3 / Vite frontend. See **快速开始** above — commands are the same.
