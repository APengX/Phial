"""Extract each HTML document into a parallel Markdown text layer.

The .html files in the workspace are the raw sources — Phial never modifies
them. This module derives a separate Markdown layer under `.phial/text/`,
mirroring the document tree: `notes/plan.html` -> `.phial/text/notes/plan.md`.
The `.phial/` folder starts with a dot, so the file tree (which skips dotted
entries) never shows it.

The Markdown keeps the structure that matters for building a knowledge graph
later — headings, lists, blockquotes, tables, and links. An <a href> that
points at another workspace document is rewritten to a relative link between
the corresponding `.md` files, so the graph can be built straight off the
text layer (the "LLM Wiki" pattern).

Extraction is never automatic — it runs only when explicitly requested.
"""

import posixpath
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString, Tag

from ..utils.logger import get_logger
from .doc_graph import _resolve_href
from .workspace import Workspace, WorkspaceError

logger = get_logger("phial.doc_text")

# Folder (workspace-relative) that holds the derived Markdown layer.
TEXT_DIR = ".phial/text"

# Skip absurdly large documents so a bulk extract stays fast.
_MAX_SCAN_BYTES = 5 * 1024 * 1024

_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# Block containers we descend into rather than rendering directly.
_CONTAINERS = {
    "div", "section", "article", "main", "header", "footer", "aside",
    "nav", "figure", "figcaption", "details", "summary", "fieldset",
}


# --- path helpers ------------------------------------------------------------

def _md_rel(doc_rel: str) -> str:
    """`notes/plan.html` -> `notes/plan.md` (workspace-relative)."""
    stem = re.sub(r"\.html?$", "", doc_rel, flags=re.IGNORECASE)
    return stem + ".md"


def text_path(doc_rel: str):
    """Absolute path of the `.md` sidecar for a document."""
    return Workspace.root() / TEXT_DIR / _md_rel(doc_rel)


# --- plain text (for phrase matching) ----------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_MARKER_RE = re.compile(r"(?m)^\s{0,3}(?:#{1,6}|>|[-*+]|\d+\.)\s+")


def markdown_plain_text(md: str) -> str:
    """Reduce a text-layer page to plain prose, for phrase matching.

    Drops the frontmatter, code, images and *links* — already-linked text must
    not be re-proposed as a new link — and strips Markdown markers."""
    if not md:
        return ""
    s = _FRONTMATTER_RE.sub("", md, count=1)
    s = _FENCE_RE.sub(" ", s)
    s = _IMG_RE.sub(" ", s)
    s = _LINK_RE.sub(" ", s)
    s = _INLINE_CODE_RE.sub(" ", s)
    s = _MARKER_RE.sub("", s)
    return s.replace("|", " ").replace("*", "").replace("~", "")


def without_frontmatter(md: str) -> str:
    """Drop the leading YAML frontmatter block from a text-layer page."""
    return _FRONTMATTER_RE.sub("", md or "", count=1)


# --- inline rendering --------------------------------------------------------

def _collapse_ws(text: str) -> str:
    return re.sub(r"[ \t\r\n]+", " ", text)


def _link(a: Tag, ctx: dict) -> str:
    label = _inline(a, ctx).strip()
    href = (a.get("href") or "").strip()
    if not href:
        return label
    target = _resolve_href(href, ctx["from_dir"], ctx["doc_set"])
    if target:
        # internal doc link -> relative path between the two .md files
        rel = posixpath.relpath(_md_rel(target), ctx["md_dir"] or ".")
        href = rel
    label = label or href
    return f"[{label}]({href})"


def _img(node: Tag) -> str:
    src = (node.get("src") or "").strip()
    alt = (node.get("alt") or "").strip()
    return f"![{alt}]({src})" if src else ""


def _inline(node, ctx: dict) -> str:
    """Render the inline content of a node to Markdown."""
    parts = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(_collapse_ws(str(child)))
        elif isinstance(child, Tag):
            name = child.name.lower()
            if name == "br":
                parts.append("  \n")
            elif name in ("strong", "b"):
                inner = _inline(child, ctx).strip()
                parts.append(f"**{inner}**" if inner else "")
            elif name in ("em", "i"):
                inner = _inline(child, ctx).strip()
                parts.append(f"*{inner}*" if inner else "")
            elif name in ("code", "kbd", "samp"):
                inner = child.get_text().strip()
                parts.append(f"`{inner}`" if inner else "")
            elif name == "a":
                parts.append(_link(child, ctx))
            elif name == "img":
                parts.append(_img(child))
            else:
                parts.append(_inline(child, ctx))
    return _collapse_ws("".join(parts)).strip()


# --- block rendering ---------------------------------------------------------

def _list(node: Tag, ctx: dict, ordered: bool, depth: int = 0) -> str:
    lines = []
    indent = "  " * depth
    i = 1
    for li in node.find_all("li", recursive=False):
        # pull nested lists out so they render under their item
        nested = []
        for sub in li.find_all(["ul", "ol"], recursive=False):
            nested.append(_list(sub, ctx, sub.name.lower() == "ol", depth + 1))
            sub.extract()
        marker = f"{i}." if ordered else "-"
        text = _inline(li, ctx)
        lines.append(f"{indent}{marker} {text}".rstrip())
        lines.extend(n for n in nested if n)
        i += 1
    return "\n".join(lines)


def _table(node: Tag, ctx: dict) -> str:
    rows = []
    for tr in node.find_all("tr"):
        cells = [
            _inline(td, ctx).replace("|", "\\|").replace("\n", " ").strip()
            for td in tr.find_all(["td", "th"], recursive=False)
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |",
           "| " + " | ".join(["---"] * width) + " |"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _blocks(node, ctx: dict) -> list:
    """Render the block-level children of a node to a list of Markdown blocks."""
    out = []
    for child in node.children:
        if isinstance(child, NavigableString):
            txt = _collapse_ws(str(child)).strip()
            if txt:
                out.append(txt)
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in _HEADINGS:
            text = _inline(child, ctx)
            if text:
                out.append("#" * int(name[1]) + " " + text)
        elif name == "p":
            text = _inline(child, ctx)
            if text:
                out.append(text)
        elif name in ("ul", "ol"):
            block = _list(child, ctx, name == "ol")
            if block:
                out.append(block)
        elif name == "blockquote":
            inner = _blocks(child, ctx)
            quoted = "\n".join(
                "> " + line
                for block in inner
                for line in block.splitlines()
            )
            if quoted:
                out.append(quoted)
        elif name == "pre":
            code = child.get_text().rstrip("\n")
            out.append("```\n" + code + "\n```")
        elif name == "hr":
            out.append("---")
        elif name == "table":
            block = _table(child, ctx)
            if block:
                out.append(block)
        elif name == "img":
            block = _img(child)
            if block:
                out.append(block)
        elif name in _CONTAINERS or name in ("thead", "tbody", "tr", "td", "th"):
            out.extend(_blocks(child, ctx))
        elif name in ("br", "script", "style", "noscript", "template"):
            continue
        else:
            # unknown / inline-ish tag at block level: take its text
            text = _inline(child, ctx)
            if text:
                out.append(text)
    return out


def html_to_markdown(html: str, doc_rel: str, doc_set: set, title: str = "") -> str:
    """Convert one document's HTML into a Markdown page with YAML frontmatter."""
    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:  # noqa: BLE001
        soup = BeautifulSoup("", "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    body = soup.body or soup
    ctx = {
        "from_dir": posixpath.dirname(doc_rel),
        "md_dir": posixpath.dirname(_md_rel(doc_rel)),
        "doc_set": doc_set,
    }
    blocks = _blocks(body, ctx)
    text = "\n\n".join(b for b in blocks if b.strip())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    fm = (
        "---\n"
        f"title: {_yaml(title or doc_rel)}\n"
        f"source: {_yaml(doc_rel)}\n"
        f"extracted: {datetime.now(timezone.utc).isoformat()}\n"
        "---\n\n"
    )
    return fm + text + "\n"


def _yaml(value: str) -> str:
    """Quote a scalar so it is always a safe single-line YAML string."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


# --- extraction --------------------------------------------------------------

def extract_all() -> dict:
    """Extract every workspace document into `.phial/text/`; prune orphans.

    Returns {count, files, dir}."""
    root = Workspace.root()
    docs = Workspace.list_docs()
    doc_set = {d["path"] for d in docs}

    written = []
    for d in docs:
        rel = d["path"]
        if d.get("size", 0) > _MAX_SCAN_BYTES:
            logger.warning("doc_text: skipping oversized doc %s", rel)
            continue
        try:
            html = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _write_md(rel, html_to_markdown(html, rel, doc_set, d.get("title") or ""))
        written.append(_md_rel(rel))

    _prune({_md_rel(p) for p in doc_set})
    logger.info("doc_text: extracted %d documents", len(written))
    return {"count": len(written), "files": written, "dir": TEXT_DIR}


def extract_one(doc_rel: str) -> dict:
    """Extract a single document. Returns {count, files, dir}."""
    doc = Workspace.read_doc(doc_rel)
    rel = doc["path"]
    doc_set = {d["path"] for d in Workspace.list_docs()}
    _write_md(rel, html_to_markdown(doc["html"], rel, doc_set, doc.get("title") or ""))
    logger.info("doc_text: extracted %s", rel)
    return {"count": 1, "files": [_md_rel(rel)], "dir": TEXT_DIR}


def _write_md(doc_rel: str, markdown: str) -> None:
    dest = text_path(doc_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(markdown, encoding="utf-8")


def _prune(keep: set) -> None:
    """Delete `.md` files whose source document no longer exists."""
    base = Workspace.root() / TEXT_DIR
    if not base.is_dir():
        return
    for md in base.rglob("*.md"):
        rel = md.relative_to(base).as_posix()
        if rel not in keep:
            try:
                md.unlink()
            except OSError:
                pass
    # drop any directories left empty by pruning
    for d in sorted(base.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
            except OSError:
                pass
