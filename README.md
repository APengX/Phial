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
│       ├── services/     # workspace, app_settings, llm_client, html_agent, agents, cli_agent,
│       │                 # doc_text / doc_graph / doc_summary / auto_link（结构层），
│       │                 # html_style_reference（生成 prompt 的设计参考），
│       │                 # agent_guide（往工作区落 AGENTS.md / CLAUDE.md / phial-* skill）
│       └── utils/
└── frontend/             # Vue 3 + Vite + vue-router + vue-i18n + axios + CodeMirror
    └── src/
        ├── views/        # HomeView、EditorView（三栏 + 大纲/图谱侧栏 + 速读卡）、GraphView（全屏图谱）
        ├── components/   # FileTree / HtmlEditor / SandboxPreview / AiPanel / SettingsModal,
        │                 # GraphCanvas / DocOutline / DocSummary / AutoLinkModal（结构层）
        └── api/
```

- **后端**：Flask（app factory，蓝图挂 `/api/*`），`services/` 业务层；Python ≥ 3.11（实际跑 3.12），`uv` 管依赖。
- **前端**：Vue 3 + Vite，`/api` 代理到后端 `:5001`；HTML 源码用 CodeMirror 编辑。
- **生成 HTML 的 agent —— 可选**（设置里切换，详见下文「选择 agent」）：
  - **内置 LLM API**：OpenAI 兼容格式（`openai` SDK），配 `.env` 里的 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`；
  - **本地 CLI agent**：检测到 `claude`（Claude Code）/ `codex` / `gemini` 就能选，Phial 在工作区目录里以非交互模式调用它，拿回它输出的 HTML。
  - 不管选哪个，调用前都会把一份**设计语言参考文档**附进生成 prompt（暖色编辑器风、衬线标题、卡片化「30 秒速读」、Callout / 折叠块、`window.phial` 桥的用法示例），换模型也保持风格一致。
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

## 文档之间的结构（图谱 · 大纲 · 速读 · 自动链接）

一篇 `.html` 是一个独立产物，但**文档集**也应该是可看见、可导航的。Phial 在不改原始文件的前提下，给你几层结构视图：

- **🕸 文档图谱** —— 编辑器右侧栏「图谱」标签里有一张以当前文档为中心的小图；点 `⤢` 进 `/graph` 全屏视图，看整个工作区的关系。节点 = 文档；边来自两类来源：文档里真实的 `<a>` 链接、以及在「上下文」面板里勾选的跨文档引用。拖节点、滚轮缩放、点节点直接打开。
- **📄 大纲** —— 侧栏「大纲」标签，从当前文档的 h1–h3 自动抽出来，点了滚动定位。
- **⚡ 30 秒速读** —— 预览区顶部一张速读卡。按一下让模型用 3–5 条要点概括全文；结果按文档内容哈希缓存在 `~/.phial/summaries.json`，文档没改就不会重新生成。
- **🔗 自动链接（单文档）** —— 编辑器顶部 🔗 按钮扫当前这篇，发现正文里提到了工作区里别的文档的标题，弹窗让你勾选要不要包成 `<a>`。两轮：先精确匹配标题，再让 AI 找模糊 / 同义说法。Obsidian 式的「连接实体」，但你按一次确认按钮。

这套是「字符串能做的」结构。要做**字符串做不到的连接** —— 比如「这堆论文之间的关系」「这些笔记其实在讲同一件事」—— Phial 把这件事交给 Claude Code：

- **写到工作区的 agent guides** —— Phial 启动时会往工作区根目录落一组 agent 引导文件，让任何爬这个文件夹的 agent 都明白这里的输出契约：
  - `AGENTS.md` —— Phial 的完整 HTML 输出契约（自包含 HTML、禁止外部资源、`window.phial` 桥、SEARCH/REPLACE 编辑格式等）。Codex / Cursor / 通用 agent 都能读到。
  - `CLAUDE.md` —— 给 Claude Code 的精简入口，指向 `AGENTS.md` 和下面两个 skill。
  - `.claude/skills/phial-html/SKILL.md` —— 「把一个目录 / 仓库 / 一堆笔记做成一篇 Phial 文档」的 skill。
  - `.claude/skills/phial-graph/SKILL.md` —— 「**LLM Wiki**」式的连接 skill：读懂文档里在讲什么，找出真实存在的关联，写成链接，让它们在 Phial 图谱里连起来 —— 弥补字符串匹配做不到的那部分。

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
- [x] 按文档绑定的代码 / 笔记文件夹做对话上下文（首页绑文件夹「圈定范围」；编辑器侧的「📎 上下文」面板里细粒度勾要发的文件，默认一个不发；同时可跨选工作区里其它 `.html` 文档，便于互相链接）
- [x] 可视化块编辑（类 Notion）—— 编辑器顶部 `块 / 源码 / 分栏 / 预览` 四种视图。块视图基于 TipTap：`/` 召唤命令菜单、左侧拖拽手柄、Markdown 简写（`# ` `> ` `- ` ``` 等）、表格、折叠块（原生 `<details>`）、多列、Callout、图片上传/拖入/粘贴。带 `<script>` 的交互 widget 作为整段 **Widget 块**内嵌在文档里（沙箱 iframe 预览 + 「编辑 HTML」弹窗），与正文块并排存在 —— 保留 Phial 的「可操作界面」定位
- [x] 文档结构层：图谱（侧栏 + 全屏 `/graph`）、大纲（h1–h3）、AI 30 秒速读（按内容哈希缓存）、单文档自动链接（精确 + AI 模糊两轮）
- [x] LLM Wiki：往工作区写一组 agent guides（`AGENTS.md` / `CLAUDE.md` / `phial-html` / `phial-graph` skill），让 Claude Code 做字符串匹配做不到的深度连接
- [ ] CLI agent 流式更细粒度（解析 `claude --output-format stream-json`）、让它直接改文件
- [ ] 文档全文搜索、标签
- [ ] 更多内置模板（日程规划、方案对比、清单分类、表单……）
- [ ] 暴露 MCP server，让外部 agent（Claude Code / Cursor）直接驱动
- [ ] 导出（单文件 HTML / PDF / Markdown）、版本历史
- [ ] 块编辑器扩展：链接富预览、表格 cell 合并、图片 out-of-line 存到工作区资产目录

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

**Structure across documents**: the editor side-rail has an Outline (h1–h3), a Graph mini-map (full-screen view at `/graph`), and a `🔗` auto-link button that finds mentions of other documents in the workspace. The preview column shows an AI-generated **30-second read** card, cached by content hash. For deeper, semantic linking that string matching can't do, Phial drops a set of agent guides into the workspace (`AGENTS.md`, `CLAUDE.md`, plus `phial-html` and `phial-graph` skills) so Claude Code can build an **LLM Wiki** across your documents.

**Pluggable agents**: in Settings (⚙) you can use the built-in OpenAI-compatible client (configured in `.env`) or, if Phial detects them on your PATH, a local CLI agent — `claude` (Claude Code), `codex`, or `gemini` — with its own model and environment variables. Phial invokes the CLI non-interactively in the workspace folder and extracts the HTML it prints. Every generation call carries a built-in **design-language reference** so output stays consistent across models.

Stack: Flask backend (app-factory + blueprints, `uv`) + Vue 3 / Vite frontend. See **快速开始** above — commands are the same.
