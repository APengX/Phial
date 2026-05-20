"""Auto-linking: turn mentions of other documents into internal links.

Obsidian-style "connect the entities" — given the document you're editing, find
words in its body that name another document in the workspace and wrap them in
an <a> pointing at that document. Two passes:

  1. exact   — deterministic scan: a verbatim occurrence of another document's
               title (word-boundary aware for ASCII) becomes a candidate.
  2. ai      — the API hands the remaining (un-matched) documents to the
               configured model, which spots fuzzy / synonym mentions.

`exact_candidates` + `parse_ai` only *find* candidates; the editor previews them
and the user confirms which to keep. `apply_links` then wraps the chosen
phrases. Links are plain relative hrefs so `doc_graph` picks them up as edges.
"""

import json
import posixpath
import re
from typing import List

from bs4 import BeautifulSoup, NavigableString

from . import doc_summary
from .workspace import Workspace
from ..utils.logger import get_logger

logger = get_logger("phial.auto_link")

# Text inside these tags is never linked (already a link, code, markup, ...).
_SKIP_TAGS = {"a", "script", "style", "pre", "code", "head", "title",
              "textarea", "noscript"}

# Titles too generic to be worth linking on.
_GENERIC_TITLES = {"无标题", "新文档", "untitled", "document", "新建文档"}

# Cap how much text the AI pass sees, and how many targets it's offered.
_MAX_TARGETS = 240

_ASCII_RE = re.compile(r"[\x00-\x7f]+")


def _is_ascii_word(s: str) -> bool:
    """ASCII titles need word boundaries ('art' must not match 'start');
    CJK titles have no word boundaries, so a plain substring match is fine."""
    return bool(_ASCII_RE.fullmatch(s))


def _first_index(text: str, phrase: str) -> int:
    """Index of the first occurrence of `phrase` in `text`, or -1.

    Case-insensitive; ASCII phrases must sit on word boundaries."""
    if not phrase:
        return -1
    if _is_ascii_word(phrase):
        m = re.search(
            r"(?<![0-9A-Za-z])" + re.escape(phrase) + r"(?![0-9A-Za-z])",
            text, re.IGNORECASE,
        )
        return m.start() if m else -1
    return text.lower().find(phrase.lower())


def _snippet(text: str, idx: int, length: int, pad: int = 36) -> str:
    """A short context window around a match, for the preview UI."""
    start = max(0, idx - pad)
    end = min(len(text), idx + length + pad)
    out = text[start:end].replace("\n", " ").strip()
    if start > 0:
        out = "…" + out
    if end < len(text):
        out = out + "…"
    return out


def _in_skip(node) -> bool:
    for parent in node.parents:
        if getattr(parent, "name", None) in _SKIP_TAGS:
            return True
    return False


# --- targets -----------------------------------------------------------------

def _all_targets() -> List[dict]:
    """Every workspace document with a title worth linking to, as {path,title}."""
    out: List[dict] = []
    for d in Workspace.list_docs():
        title = (d.get("title") or "").strip()
        if len(title) < 2 or title.lower() in _GENERIC_TITLES:
            continue
        out.append({"path": d["path"], "title": title})
    return out


def collect_targets(current_path: str) -> List[dict]:
    """Every *other* document in the workspace, as {path, title} link targets."""
    cur = (current_path or "").replace("\\", "/").strip().lstrip("/")
    return [t for t in _all_targets() if t["path"] != cur][:_MAX_TARGETS]


# --- pass 1: exact title match -----------------------------------------------

def exact_candidates(html: str, targets: List[dict]) -> List[dict]:
    """Find verbatim occurrences of a target's title in the document body.

    One candidate per target — the first place its title appears in linkable
    text. Longer titles win when two titles overlap at the same spot."""
    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:  # noqa: BLE001
        return []
    body = soup.body or soup

    # Concatenate linkable text once; this is only used to locate matches.
    chunks: List[str] = []
    for node in body.find_all(string=True):
        if _in_skip(node):
            continue
        chunks.append(str(node))
    text = " ".join(chunks)
    if not text.strip():
        return []

    found: List[dict] = []
    for tgt in sorted(targets, key=lambda t: len(t["title"]), reverse=True):
        title = tgt["title"]
        idx = _first_index(text, title)
        if idx < 0:
            continue
        found.append({
            "phrase": text[idx:idx + len(title)],
            "target": tgt["path"],
            "title": title,
            "kind": "exact",
            "snippet": _snippet(text, idx, len(title)),
        })
    return found


def scan_workspace() -> List[dict]:
    """Exact-match auto-link across the whole workspace.

    Returns one group per source document that has candidates:
      [{path, title, candidates:[{id,phrase,target,title,kind,snippet}]}]
    Exact-only — fast, deterministic, no model calls — so a "link everything"
    sweep stays instant. The AI pass is the per-document feature."""
    docs = Workspace.list_docs()
    targets = _all_targets()
    groups: List[dict] = []
    for d in docs:
        path = d["path"]
        doc_targets = [t for t in targets if t["path"] != path][:_MAX_TARGETS]
        if not doc_targets:
            continue
        try:
            html = Workspace.read_doc(path)["html"]
        except Exception:  # noqa: BLE001
            continue
        cands = exact_candidates(html, doc_targets)
        if not cands:
            continue
        for i, c in enumerate(cands):
            c["id"] = i
        groups.append({
            "path": path,
            "title": d.get("title") or path,
            "candidates": cands,
        })
    return groups


# --- pass 2: AI fuzzy match --------------------------------------------------

_SYSTEM_PROMPT = """你是 Phial 的「自动链接」助手。

用户会给你两样东西：
1. 当前文档的正文文字。
2. 工作区里其他文档的标题清单，每条带一个 path。

你的任务：在正文里找出**明确指代清单中某篇文档主题**的词语或短语，把它和那篇文档配成一对。这样读者就能从这篇文档跳到相关的另一篇。

规则：
- phrase 必须是正文里**逐字出现**的连续片段，原样照抄（含大小写、标点）。
- 只链接确实在讲那个主题的词；只是字面巧合、泛泛相关的不要配。
- 同一个词只配一次；拿不准就不要配。
- 一篇目标文档最多配一个词。
- 只输出一个 JSON 数组，不要任何解释、不要 Markdown 代码围栏。

输出格式（path 必须照抄清单里的）：
[{"phrase": "正文里的词", "path": "目标文档的 path"}]
没有合适的就输出 []"""

_USER_TEMPLATE = """## 当前文档正文（已抽取为纯文字）
{text}

## 可链接的目标文档
{targets}

请输出 JSON 数组。"""


def _targets_block(targets: List[dict]) -> str:
    return "\n".join(f"- [{t['path']}] {t['title']}" for t in targets)


def build_messages(html: str, targets: List[dict]) -> List[dict]:
    text = doc_summary.extract_text(html) or "(空文档)"
    user = _USER_TEMPLATE.format(text=text, targets=_targets_block(targets))
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_prompt(html: str, targets: List[dict]) -> str:
    """Flatten the messages into a single prompt string for CLI agents."""
    return "\n\n---\n\n".join(m["content"].strip()
                              for m in build_messages(html, targets))


def _extract_json_array(raw: str):
    """Pull the first JSON array out of a model reply (tolerates code fences)."""
    if not raw:
        return []
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    start = s.find("[")
    end = s.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(s[start:end + 1])
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def parse_ai(raw: str, html: str, targets: List[dict]) -> List[dict]:
    """Turn a model reply into validated candidates.

    Drops anything whose phrase doesn't actually appear in the body or whose
    path isn't a real target; keeps one candidate per (phrase, target)."""
    text = doc_summary.extract_text(html)
    by_path = {t["path"]: t["title"] for t in targets}
    out: List[dict] = []
    seen = set()
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        phrase = (item.get("phrase") or "").strip()
        path = (item.get("path") or item.get("target") or "").strip()
        if not phrase or path not in by_path:
            continue
        key = (phrase.lower(), path)
        if key in seen:
            continue
        idx = _first_index(text, phrase)
        if idx < 0:
            continue
        seen.add(key)
        out.append({
            "phrase": text[idx:idx + len(phrase)],
            "target": path,
            "title": by_path[path],
            "kind": "ai",
            "snippet": _snippet(text, idx, len(phrase)),
        })
    return out


# --- apply -------------------------------------------------------------------

def _wrap_first(soup: BeautifulSoup, phrase: str, href: str) -> bool:
    """Wrap the first linkable occurrence of `phrase` in an <a href>."""
    for node in soup.find_all(string=True):
        if _in_skip(node):
            continue
        s = str(node)
        idx = _first_index(s, phrase)
        if idx < 0:
            continue
        before, match, after = s[:idx], s[idx:idx + len(phrase)], s[idx + len(phrase):]
        a = soup.new_tag("a", href=href)
        a["class"] = "phial-link"
        a.string = match
        pieces = []
        if before:
            pieces.append(NavigableString(before))
        pieces.append(a)
        if after:
            pieces.append(NavigableString(after))
        node.replace_with(*pieces)
        return True
    return False


def apply_links(current_path: str, html: str, picks: List[dict]) -> tuple:
    """Wrap each picked phrase in a link to its target document.

    `picks` is [{phrase, target}]. Returns (new_html, applied_count). Each
    phrase is linked once, at its first occurrence; href is relative to the
    current document so doc_graph resolves it as a link edge."""
    soup = BeautifulSoup(html or "", "html.parser")
    from_dir = posixpath.dirname((current_path or "").replace("\\", "/").lstrip("/"))
    used = set()
    applied = 0
    for pick in picks:
        if not isinstance(pick, dict):
            continue
        phrase = (pick.get("phrase") or "").strip()
        target = (pick.get("target") or "").strip().replace("\\", "/").lstrip("/")
        if not phrase or not target:
            continue
        key = phrase.lower()
        if key in used:
            continue
        href = posixpath.relpath(target, from_dir or ".")
        if _wrap_first(soup, phrase, href):
            used.add(key)
            applied += 1
    return str(soup), applied
