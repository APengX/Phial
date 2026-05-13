"""Builds prompts for generating / editing HTML *documents and interfaces*, and
extracts the final HTML out of an LLM reply.

Phial's contract with the model: output a single, self-contained HTML file.
Crucially — when the user's intent is to *manipulate* things (reorder, pick,
tune, compare, iterate), the model should build a working UI, not a write-up,
and wire it to the `window.phial` bridge that Phial injects at render time so
the user's actions flow back into the conversation.
"""

import json
import re
from typing import Any, List, Optional

_SYSTEM_PROMPT = """你是 Phial 的内容 / 界面生成引擎。

Phial 用 HTML 作为原生格式：每个文档是一个独立的 .html 文件，渲染在一个沙箱 iframe 里展示给用户。但 Phial 的重点不是"排版好看的文档"——HTML 相对 Markdown 的核心价值在于：它不只承载文字，还承载**布局、图示、交互、视觉层级**。所以你产出的东西经常应该是一个**可以操作的界面**，而不是一篇等人线性阅读的文章。人在做判断时，往往不是读，而是在比较、移动、筛选、调参、反复看效果——HTML 要把这些动作接住。

先判断该产出什么：
- 用户要的是知识 / 说明 / 记录 / 报告 → 产出排版讲究的**文档**：语义化标签、清晰的视觉层级、合理留白、表格、`<details>` 折叠、内联 SVG 图示、提示框等。
- 用户的意图涉及**排序 / 拖动 / 筛选 / 勾选 / 选择 / 调参 / 对比方案 / 反复预览**（例：给 30 个 ticket 排优先级、调一个 system prompt、规划一周日程、给一堆条目分类、对比几个候选）→ 产出一个**真正能用的界面**：可拖拽的卡片、可编辑的字段、实时预览、滑块、勾选框、分栏看板……让用户直接在里面操作，最后一键把结果带走，而不是回聊天框一条条口述。

Phial 在渲染时会向文档注入一个宿主桥 `window.phial`（你可以在文档的 `<script>` 里直接调用，它一定存在）：
- `phial.setState(obj)` —— 把"当前界面状态"上报给 Phial（比如重新排好的看板、用户的勾选、编辑后的 prompt 文本）。**每当用户的操作改变了状态就调用它**。这个状态会作为上下文自动附在用户下一条消息里发回给你，你就能接着上一步继续。
- `phial.sendToAgent(summaryText, obj?)` —— 一键把结果回传给 AI 并立刻触发新一轮对话。把它接到界面里的**主操作按钮**上，比如「确认这个排序」「导出为 Markdown 并发回」「应用这个 prompt」。`summaryText` 是给 AI 看的简短自然语言说明，`obj` 是结构化数据（可选）。
- `phial.ready()` —— 可选，文档初始化完成后调用一次。

硬性约定：
1. 始终输出**一个完整、自包含的 HTML 文档**：`<!DOCTYPE html>`、`<html>`、`<head>`（含 `<meta charset="UTF-8">` 和恰当的 `<title>`）、`<body>`。
2. 所有 CSS 写进文档内的 `<style>`，所有交互写进文档内的 `<script>`。**禁止引用任何外部网络资源**——外部 CSS / JS / 字体 / 图片 URL、CDN 上的拖拽库等都会被沙箱拦截。拖拽用原生 HTML5 Drag and Drop 或 Pointer 事件**自己写**；图标 / 图示用内联 SVG 或 emoji；不要 `fetch`。
3. **不要用 `window.prompt` / `alert` / `confirm`**——文档跑在跨源沙箱 iframe 里，浏览器会静默拦截它们（点了没反应）。需要用户输入就放页面内的 `<input>` / `contenteditable` / `<textarea>`；需要确认就用页面内的按钮 / 二次点击。
4. **数据直接写进 HTML**（那 30 个 ticket 就内联成 DOM 节点或一个 JS 数组），不要去网络拿。
5. 交互要"真"：能拖就真的能拖、能编辑就真的能改、预览要实时刷新；状态变了就 `phial.setState(...)`；放一个明确的主按钮 `phial.sendToAgent(...)`。别做"假"的可视化——不要只是把 Markdown 套层 CSS。
6. 中文文档默认用系统中文字体栈（`-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`）；克制、可读、视觉层级清晰；适配窄屏。
7. 直接输出 HTML 本身（可以放在 ```html 代码块里，也可以裸输出）；不要在 HTML 之外写多余的解释。"""

_CREATE_TEMPLATE = """请新建一个 HTML 文档 / 界面。

需求：
{request}

输出完整的 HTML。"""

_EDIT_TEMPLATE = """这是当前文档的 HTML：

```html
{current_html}
```

本次是**修改这份现有文档**，不要重新输出整篇——只给改动的片段（这条优先于上面"始终输出完整 HTML"的说明）。
用一个或多个下面这种块表示改动：

<<<<<<< SEARCH
（从当前文档里逐字符复制的一小段，必须和原文完全一致，包括缩进、空白、换行）
=======
（要替换成的新内容）
>>>>>>> REPLACE

规则：
- 每个 SEARCH 块要能在当前文档里**唯一匹配到一处**——多带几行上下文确保唯一；不要带行号。
- 新增内容时：SEARCH 放一段紧挨着插入点的现有代码，REPLACE 放"那段现有代码 + 你要加的新内容"。
- 删除内容时：REPLACE 留空。
- SEARCH 块可以为空，表示把 REPLACE 的内容追加到 `</body>` 之前。
- 多处改动给多个块，顺序随意。
- 除了这些块之外不要输出别的（不要解释、不要再贴整篇 HTML）。

要求：

{request}"""

_STATE_BLOCK = """用户当前在这个界面里的操作结果（请据此理解他们想要什么 / 把它纳入修改）：
```json
{state}
```"""

_PICKED_BLOCK = """用户在预览里**选中了下面这个元素**——请把改动聚焦在它身上。

```html
{html}
```

CSS 选择器（仅供参考）：`{selector}`

定位策略：
- 如果你能在"当前文档 HTML"里**逐字符**找到这段 outerHTML，就把它整段作为一个 SEARCH 块、修改后的版本作为 REPLACE。
- 如果找不到（通常是因为它是 JS 动态生成的），就在当前文档的源代码里找**生成它的那部分代码**（模板、数据数组、render 函数等），改那里。"""


def _format_state(state: Any) -> Optional[str]:
    if state is None or state == "" or state == {} or state == []:
        return None
    if isinstance(state, str):
        return _STATE_BLOCK.format(state=state.strip())
    try:
        return _STATE_BLOCK.format(state=json.dumps(state, ensure_ascii=False, indent=2))
    except (TypeError, ValueError):
        return _STATE_BLOCK.format(state=str(state))


def _format_picked(picked: Any) -> Optional[str]:
    if not picked or not isinstance(picked, dict):
        return None
    html = (picked.get("outerHTML") or "").strip()
    if not html:
        return None
    return _PICKED_BLOCK.format(html=html, selector=picked.get("selector") or "")


def build_messages(
    prompt: str,
    current_html: Optional[str] = None,
    interface_state: Any = None,
    picked_element: Any = None,
) -> List[dict]:
    prompt = (prompt or "").strip()
    parts: List[str] = []
    picked_block = _format_picked(picked_element)
    if picked_block:
        parts.append(picked_block)
    state_block = _format_state(interface_state)
    if state_block:
        parts.append(state_block)
    if prompt:
        parts.append(prompt)
    request = "\n\n".join(parts) if parts else "（无具体要求，请合理发挥）"

    if current_html and current_html.strip():
        user = _EDIT_TEMPLATE.format(current_html=current_html.strip(), request=request)
    else:
        user = _CREATE_TEMPLATE.format(request=request)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_prompt(
    prompt: str,
    current_html: Optional[str] = None,
    interface_state: Any = None,
    picked_element: Any = None,
) -> str:
    """A single text prompt (system instructions + user request) for CLI agents
    that take one prompt string rather than a messages array."""
    msgs = build_messages(prompt, current_html, interface_state, picked_element)
    return msgs[0]["content"].rstrip() + "\n\n---\n\n" + msgs[1]["content"].strip()


_FENCE_RE = re.compile(r"```(?:html|HTML)?\s*\n?(.*?)```", re.DOTALL)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE html.*?</html\s*>", re.DOTALL | re.IGNORECASE)
_HTMLTAG_RE = re.compile(r"<html[\s>].*?</html\s*>", re.DOTALL | re.IGNORECASE)


def extract_html(reply: str) -> str:
    """Pull the HTML document out of a model reply, tolerating code fences and
    stray prose around it. Falls back to the raw reply if nothing matches."""
    if not reply:
        return ""
    text = reply.strip()

    fenced = _FENCE_RE.findall(text)
    if fenced:
        text = max(fenced, key=len).strip()

    m = _DOCTYPE_RE.search(text)
    if m:
        return m.group(0).strip()

    m = _HTMLTAG_RE.search(text)
    if m:
        return _ensure_doctype(m.group(0).strip())

    if "<" in text and ">" in text:
        return _wrap_fragment(text)

    return text


def _ensure_doctype(html: str) -> str:
    if html.lstrip().lower().startswith("<!doctype"):
        return html
    return "<!DOCTYPE html>\n" + html


def _wrap_fragment(fragment: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="zh">\n<head>\n  <meta charset="UTF-8">\n'
        "  <title>Untitled</title>\n</head>\n<body>\n" + fragment + "\n</body>\n</html>\n"
    )


# ---- SEARCH/REPLACE edit blocks -----------------------------------------------

_EDIT_BLOCK_RE = re.compile(
    r"<{5,}\s*SEARCH[^\n]*\n(.*?)^={5,}[^\n]*\n(.*?)^>{5,}\s*REPLACE",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)


def _parse_edit_blocks(reply: str):
    """List of (search, replace) pairs found in a model reply."""
    return [(m.group(1), m.group(2)) for m in _EDIT_BLOCK_RE.finditer(reply or "")]


def _try_replace(text: str, search: str, replace: str):
    """Replace the first occurrence of `search` in `text`. Tolerates the model
    adding/dropping surrounding whitespace. Returns (new_text, matched?)."""
    for s, r in ((search, replace),
                 (search.strip("\n"), replace.strip("\n")),
                 (search.strip(), replace.strip())):
        if s and s in text:
            return text.replace(s, r, 1), True
    return text, False


def _apply_edit_blocks(html: str, blocks):
    result = html
    applied = 0
    failed = []
    for search, replace in blocks:
        if not search.strip():
            # empty SEARCH -> append the new content just before </body>
            m = re.search(r"</body\s*>", result, re.IGNORECASE)
            chunk = replace.strip("\n")
            if m:
                result = result[: m.start()] + chunk + "\n" + result[m.start():]
            else:
                result = result.rstrip() + "\n" + chunk + "\n"
            applied += 1
            continue
        result, matched = _try_replace(result, search, replace)
        if matched:
            applied += 1
        else:
            first_line = next((ln for ln in search.splitlines() if ln.strip()), search.strip())
            failed.append(first_line.strip()[:80])
    return result, applied, failed


def _has_full_doc(reply: str) -> bool:
    return bool(_DOCTYPE_RE.search(reply or "") or _HTMLTAG_RE.search(reply or ""))


def finalize_html(reply: str, current_html: Optional[str]) -> dict:
    """Turn a model reply into the document's new HTML.

    - no current doc        -> the reply is a full document
    - reply has S/R blocks  -> apply them to current_html  (mode="patch")
    - reply is a full doc   -> use it as-is                (mode="full")
    - otherwise             -> keep current_html unchanged (mode="noop")
    """
    if not (current_html and current_html.strip()):
        return {"html": extract_html(reply), "mode": "full"}

    blocks = _parse_edit_blocks(reply)
    if blocks:
        new_html, applied, failed = _apply_edit_blocks(current_html, blocks)
        if applied == 0 and _has_full_doc(reply):
            return {"html": extract_html(reply), "mode": "full"}
        return {"html": new_html, "mode": "patch", "applied": applied, "failed": failed}

    if _has_full_doc(reply):
        return {"html": extract_html(reply), "mode": "full"}
    return {"html": current_html, "mode": "noop"}
