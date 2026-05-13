"""Drop an "agent bundle" into the workspace root so any agent that crawls
or loads the folder learns what Phial expects.

Three files are dropped, covering three loading paths:

  - `AGENTS.md`
      Passive reference. Codex / Cursor / generic agents discover it when
      they list the folder.

  - `CLAUDE.md`
      Claude Code reads this into context automatically at session start.
      It's deliberately short — it points at AGENTS.md (full contract) and
      at the skill below.

  - `.claude/skills/phial-html/SKILL.md`
      Project-level skill for Claude Code. Triggered when the user asks
      to "turn a folder / repo / directory of notes into a Phial
      document/interface". Takes a path, walks it, decides
      document-vs-interface, emits one self-contained `.html` into this
      workspace.

So *whoever* opens the folder — a CLI that reads docs, Claude Code with
auto-loaded CLAUDE.md, Claude Code being asked to ingest some other folder
— ends up emitting Phial-compatible HTML.

Write-once per (workspace, file). `ensure(root)`:
  - leaves any existing file alone (the user may have edited it);
  - if a file is missing AND we've already recorded that (root, file)
    pair, also leaves it alone (user deleted it on purpose);
  - otherwise writes a fresh copy and records the pair in
    `~/.phial/settings.json` under `agent_guides_written`.

Legacy: pre-bundle settings tracked roots only. Bare-root entries are
migrated implicitly as "{root}::AGENTS.md" on read.
"""

from pathlib import Path
from typing import List, Tuple

from ..utils.logger import get_logger
from . import app_settings

logger = get_logger("phial.agent_guide")

AGENT_GUIDE_NAME = "AGENTS.md"
CLAUDE_MD_NAME = "CLAUDE.md"
SKILL_REL_PATH = Path(".claude") / "skills" / "phial-html" / "SKILL.md"

_SETTINGS_KEY = "agent_guides_written"
_SEPARATOR = "::"


# ---------------------------------------------------------------------------
# Bundle contents. Kept inline so the install is self-contained (no extra
# files to ship). Edit these strings when the contract changes; existing
# workspaces won't be auto-updated (write-once), but new ones will pick it up.
# ---------------------------------------------------------------------------

AGENT_GUIDE_CONTENT = """# Phial 工作区 · 给 agent 看的说明书

这个文件夹是一个 **Phial** 工作区。Phial 是一个轻量编辑器：每个 `.html` 文件就是一篇文档，渲染时被放进一个跨源沙箱 iframe 里展示给用户。所以 HTML 在这里不只是承载文字，更承载**布局、图示、交互、视觉层级**——很多时候你产出的应该是**一个能操作的界面**，而不是一篇等人线性读的文章。

如果你（Claude Code / Codex / Cursor / MCP server / 普通脚本 / 任何会读这个文件的 agent）正在往这个文件夹写文件，按下面的规则来，确保 Phial 能正确渲染、用户能继续在 Phial 里编辑。

## 一个 `.html` 文件 = 一篇文档

- 文件名 kebab-case，扩展名 `.html`，描述性强（`q3-roadmap.html`，不是 `untitled-3.html`）。子目录随意，路径就是 Phial 用来定位文档的 slug。
- 标题取自 `<title>`（缺则回退到首个 `<h1>`）。
- 不需要 dev server、不需要构建、不需要编译——直接把 `.html` 文件写到这个文件夹里就行，Phial 会自动看到并显示在侧边栏。

## 每个文档必须满足

1. **完整且自包含**：`<!DOCTYPE html>`、`<html>`、`<head>`（含 `<meta charset="UTF-8">` 和恰当的 `<title>`）、`<body>`。
2. 所有 CSS 写进文档内的 `<style>`，所有 JS 写进文档内的 `<script>`。
3. **禁止引用任何外部网络资源**——外部 CSS / JS / 字体 / 图片 / CDN 上的库都会被沙箱拦截。
   - 拖拽用原生 HTML5 Drag and Drop / Pointer 事件**自己写**；
   - 图标 / 图示用内联 SVG 或 emoji；
   - 不要 `fetch()` 外部地址，数据直接内联进 HTML（DOM 节点或 JS 数组）。
4. **不要用 `window.prompt` / `alert` / `confirm`**——文档跑在跨源沙箱 iframe 里，浏览器会静默拦截（点了没反应）。需要输入就放页面内 `<input>` / `<textarea>` / `contenteditable`；需要确认就用页面内的按钮 / 二次点击。
5. 中文文档默认用系统中文字体栈：`-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`。视觉上克制、可读、层级清晰，适配窄屏。

## 先判断：文档 还是 界面？

- 用户要的是**知识 / 说明 / 记录 / 报告** → 产出排版讲究的**文档**：语义化标签、清晰的视觉层级、合理留白、表格、`<details>` 折叠、内联 SVG 图示、提示框等。
- 用户的意图涉及**排序 / 拖动 / 筛选 / 勾选 / 选择 / 调参 / 对比方案 / 反复预览**（例：给 30 个 ticket 排优先级、调一个 system prompt、规划一周日程、给条目分类、对比候选）→ 产出**真正能用的界面**：可拖拽的卡片、可编辑的字段、实时预览、滑块、勾选框、分栏看板……让用户直接在里面操作，最后一键把结果带走。

别只是把 Markdown 套一层 CSS 装成"可视化"——能拖就真的能拖、能编辑就真的能改、预览要实时刷新。

## `window.phial` —— 文档 ↔ 上游 AI 的两向桥

Phial 在渲染时会向文档注入一个全局对象 `window.phial`。你可以在文档的 `<script>` 里直接调用，它**一定存在**：

```html
<script>
  // 1) 把"当前界面状态"上报给 Phial。每当用户的操作改变了状态就调用它。
  //    这个状态会自动附在用户下一条消息里发回给上游 AI——意味着 AI 能接着上一步继续。
  phial.setState({ /* 任意可序列化对象：你定义的结构 */ });

  // 2) 一键把结果回传给 AI 并立刻触发新一轮对话。
  //    把它接到界面里的**主操作按钮**上："确认这个排序" / "导出为 Markdown 并发回" / "用这版 prompt"。
  phial.sendToAgent("简短的人话总结，给 AI 看", {
    /* 可选的结构化数据 */
  });

  // 3) 可选：文档初始化完成后调用一次。
  phial.ready();
</script>
```

这三个钩子合起来就是"用户在文档里操作 → AI 看到 → 文档被改 → 再操作"的循环。把它接上，文档才能从一篇"展示物"升级成一个**可以一起干活的界面**。

## 编辑现有文档时的输出格式

如果用户传给你的 prompt 里附了"这是当前文档的 HTML"并要求**修改它**，输出 SEARCH/REPLACE 块即可，每块格式：

```
<<<<<<< SEARCH
（从当前文档里逐字符复制的一小段，必须和原文完全一致）
=======
（要替换成的新内容）
>>>>>>> REPLACE
```

- SEARCH 块要能在原文里**唯一匹配到一处**，多带几行上下文确保唯一。
- 新增内容时：SEARCH 放一段紧挨着插入点的现有代码，REPLACE 放"那段现有代码 + 你要加的新内容"。
- 删除内容时：REPLACE 留空。
- 多处改动给多个块。

新建文档时正常输出**完整 HTML**，不要给 SEARCH/REPLACE 块。

## 把"别的文件夹"做成 Phial 文档

如果用户让你**读取另一个文件夹**（一份代码库、一堆笔记、一个数据目录）然后产出 Phial 文档，看一下同目录下的 `.claude/skills/phial-html/SKILL.md`——里面有 step-by-step 的做法（Claude Code 可以直接用 Skill 工具调用 `phial-html`）。

---

*这个文件是 Phial 第一次接管这个文件夹时自动生成的。你可以自由编辑——只要文件存在，Phial 就不会覆盖它；删除它之后 Phial 也会记住、不会再生成。*
"""


CLAUDE_MD_CONTENT = """# Phial 工作区 · Claude Code 指引

这个文件夹是一个 **Phial** 工作区。每个 `.html` 文件就是一篇文档，被 Phial 放进一个跨源沙箱 iframe 里渲染。所以你写到这里的 HTML 不是"网页"——是一份**可移植、自包含、能在 Phial 里被人继续操作**的产物。

## 先看这两份

- **[`AGENTS.md`](./AGENTS.md)** —— Phial 的完整输出契约（自包含 HTML、禁止外部资源、`window.phial` 桥、SEARCH/REPLACE 编辑格式等）。**任何往这里写文件的动作之前都先读它**。
- **[`.claude/skills/phial-html/SKILL.md`](./.claude/skills/phial-html/SKILL.md)** —— 项目级 skill。当用户说"把 `~/foo` 这个目录 / 这个仓库 / 这堆笔记**做成一篇 Phial 文档**"时，用 `Skill` 工具调用 `phial-html`（或者直接照着里面的步骤来）。

## 硬性约定速查

写到这个文件夹的每个 `.html`：

1. 完整自包含：`<!DOCTYPE html>` + `<html>` + `<head>`（含 `<meta charset="UTF-8">` 和 `<title>`）+ `<body>`；CSS 进 `<style>`，JS 进 `<script>`。
2. **不引外部网络资源**——CDN、Google Fonts、远端图片、`fetch()` 远程都会被沙箱拦。数据直接内联到 HTML 里。
3. 不要 `window.prompt` / `alert` / `confirm`——跨源 iframe 里被静默拦截。用页面内 `<input>` / 按钮代替。
4. 调用 `window.phial`：状态变化时 `phial.setState(...)`，主按钮接 `phial.sendToAgent(summary, payload)`，可选地启动时 `phial.ready()`。
5. 先判断该产"文档"还是"界面"——涉及排序 / 拖动 / 筛选 / 调参 / 对比时，做**真能操作**的界面，不是 Markdown 套层 CSS。

## 修改既有文档

如果用户让你改这个工作区里已有的某个 `.html`（你已经看过它的源码），优先输出 SEARCH/REPLACE 块（见 AGENTS.md），不要重新整篇粘贴。

---

*这个文件由 Phial 自动生成于第一次接管该工作区时。删除后 Phial 记得这件事，不会再恢复。*
"""


SKILL_CONTENT = """---
name: phial-html
description: Read a folder (a codebase, a directory of notes, a pile of scratch files, a data dump) and produce one self-contained Phial-compatible .html document inside the current Phial workspace. Use when the user asks to "turn / make / convert / 整理 / 做成 a folder/repo/directory into a Phial document or interface" — e.g. "把 ~/notes 这堆笔记整理成一份 Phial 文档", "用 phial-html 把这个仓库做成可视化概览", "read this folder and give me a draggable triage board".
---

# phial-html — folder → Phial-flavored HTML

You're inside a **Phial** workspace (the current working directory). The user wants you to read a folder — usually outside this workspace — and write **one self-contained `.html` file** here that renders correctly inside Phial's sandboxed iframe.

> `AGENTS.md` in this same workspace is the canonical Phial output contract. This skill is a specialization of it for folder-ingest work. When in doubt about formatting, defer to `AGENTS.md`.

## 1. Get the source path & intent

Take the folder path from the user's message. If they didn't give one, ask for it in one short question. Then confirm in **one** clarifying question what kind of output they want:

- **Document mode** — a written pass through the folder (overview / cheat-sheet / report / explainer / architecture map).
- **Interface mode** — something they will *operate*: drag, sort, filter, classify, compare, tune, triage. Choose this when the folder is essentially a set of items the user wants to act on.

If their phrasing already implies one (e.g. "give me an overview" → document; "排个优先级" → interface), don't ask — just announce which mode you picked in one line and proceed.

## 2. Walk the folder

Use Read / Glob / Grep against the **source path**, not the current workspace. Survey:

- **Code**: README, manifest (`package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` / similar), top-level directory layout, entry points, public API / types / commands.
- **Notes**: file listing with sizes / dates, headings, tags, internal links.
- **Data**: schema (if structured), row counts, a small representative sample.

Pull representative excerpts; do **not** dump every file. Synthesize, don't transcribe.

## 3. Decide concretely what's in the document

Before generating HTML, jot down (in your head or scratch):

- the top-level structure (sections for a document; columns/lanes/views for an interface);
- the dataset you'll inline (an array of items, a flat list, a nested tree);
- which interactions you'll wire (drag-reorder, click-to-toggle, filter input, edit-in-place);
- which user action should fire `phial.sendToAgent(...)` (this is the "I'm done — take this back to the AI" button).

## 4. Build the HTML — hard rules

1. **Complete + self-contained**: `<!DOCTYPE html>`, `<html>`, `<head>` (with `<meta charset="UTF-8">` and a real, descriptive `<title>`), `<body>`.
2. **All CSS in `<style>`, all JS in `<script>`** within the same file.
3. **Zero external resources**: no CDN libraries, no Google Fonts, no remote `<img>` URLs, no `fetch()` to network URLs. Inline every dataset and every SVG directly into the file.
4. **No `window.prompt` / `alert` / `confirm`** — the iframe sandbox silently blocks them. Use page-level `<input>` / `<textarea>` / `contenteditable` / buttons instead.
5. **Wire `window.phial`** (always available at render time inside Phial):

   ```js
   phial.ready();                                            // once at init (optional but recommended)
   phial.setState({ /* current UI state, JSON-serializable */ }); // call on every state change
   phial.sendToAgent("short human-readable summary", { /* result payload */ }); // wire to the primary button
   ```

   State and the `sendToAgent` payload are how the user's work flows back into the conversation. Design the interface so its meaningful output ends up in `state` — otherwise nothing flows back.
6. **Don't fake the interactions**: if you advertise drag-to-reorder, drag must actually reorder; edits must actually persist into state; filters must actually filter; previews must refresh live. Use native HTML5 Drag-and-Drop / Pointer events — write the drag logic yourself, don't reach for a CDN library (which would be blocked anyway).
7. Default Chinese font stack: `-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`. Restrained, readable, clear visual hierarchy, narrow-screen friendly.

## 5. Save into the workspace

Use the Write tool to put the file in the **current working directory** (this Phial workspace) at `<descriptive-kebab-case>.html` — e.g. `acme-repo-overview.html`, `q3-ticket-triage.html`, `weekly-notes-board.html`. Subfolders are fine; the relative path doubles as the document's slug in Phial's sidebar.

If the target filename is taken, either suffix with a short timestamp (`-2026-05-13`) or ask the user. Don't silently overwrite an existing document.

## 6. Hand back

Reply with **one line**:

> Wrote `<relative-path>.html`. Open it in Phial — `<one-sentence on how to operate it>` — click the primary button to send the result back to me.

Don't paste the HTML in chat. Don't narrate the contents. The user will open it.

---

## Anti-patterns

- Outputting Markdown styled with CSS and calling it a "document". HTML earns its place here by carrying **layout, interaction, hierarchy** that Markdown can't.
- A "draggable" list that only highlights on hover. Either implement real drag-reorder + state update + `phial.setState`, or fall back to clear up/down buttons that actually move items.
- Linking to CDN libraries to save effort. They are blocked by the sandbox — the file renders broken.
- A "filter" `<input>` that doesn't filter anything. Either wire it or remove it.
- Writing the file outside this workspace, or with a generic name like `output.html` / `untitled.html`.
"""


# ---------------------------------------------------------------------------
# Bundle layout & write-once bookkeeping.
# ---------------------------------------------------------------------------

# Relative path inside the workspace -> file content. Order matters only for
# the log: AGENTS.md is the "anchor" the other two reference, write it first.
_FILES: List[Tuple[Path, str]] = [
    (Path(AGENT_GUIDE_NAME), AGENT_GUIDE_CONTENT),
    (Path(CLAUDE_MD_NAME), CLAUDE_MD_CONTENT),
    (SKILL_REL_PATH, SKILL_CONTENT),
]


def _pair_key(root_key: str, rel: Path) -> str:
    return f"{root_key}{_SEPARATOR}{rel.as_posix()}"


def _migrate_entry(entry: str) -> str:
    """Pre-bundle entries were bare root paths and implicitly meant 'AGENTS.md
    was written here'. Normalize them to the new {root}::{rel} form on read."""
    if _SEPARATOR in entry:
        return entry
    return f"{entry}{_SEPARATOR}{AGENT_GUIDE_NAME}"


def _written_pairs() -> List[str]:
    raw = app_settings.get(_SETTINGS_KEY)
    if not isinstance(raw, list):
        return []
    return [_migrate_entry(str(p)) for p in raw if isinstance(p, str)]


def _record_written(pair_key: str, *, cache: List[str]) -> None:
    if pair_key in cache:
        return
    cache.append(pair_key)
    # Persist a sorted, de-duped snapshot. Sort makes the settings file
    # diffable; de-dup guards against legacy entries surviving migration.
    app_settings.set_key(_SETTINGS_KEY, sorted(set(cache)))


def ensure(root: Path, *, force: bool = False) -> List[Path]:
    """Drop the agent bundle into `root` (write-once per file unless `force`).

    Returns the list of files that were actually written this call (may be
    empty if everything was already there or previously removed by the user).
    See module docstring for the policy.
    """
    try:
        resolved = root.resolve()
    except OSError:
        return []
    root_key = str(resolved)

    # Local copy we mutate as we go; flushed to settings on every write.
    pairs: List[str] = _written_pairs()
    written: List[Path] = []

    for rel, content in _FILES:
        target = resolved / rel
        pair_key = _pair_key(root_key, rel)

        if not force:
            if target.exists():
                # File is there — remember that so we don't reconsider it.
                _record_written(pair_key, cache=pairs)
                continue
            if pair_key in pairs:
                # We wrote it once, the user removed it — respect that.
                continue

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            logger.warning("could not write %s: %s", target, exc)
            continue

        _record_written(pair_key, cache=pairs)
        logger.info("wrote agent bundle file → %s", target)
        written.append(target)

    return written
