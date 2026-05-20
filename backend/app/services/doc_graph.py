"""Build a document relationship graph for the active workspace.

Nodes are .html documents. Edges come from two sources:
  - "link"    : a link from one document to another. Taken from the Markdown
                text layer (`.phial/text/`) when a document has been extracted
                there, so manual edits to the wiki layer are reflected;
                otherwise fall back to scanning the document's <a href> tags.
  - "context" : a cross-document context pick (set in the context picker)

Nothing is persisted — the graph is derived on every request.
"""

import posixpath
import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..utils.logger import get_logger
from . import app_settings
from .workspace import Workspace

logger = get_logger("phial.doc_graph")

_DOC_EXT_RE = re.compile(r"\.html?$", re.IGNORECASE)
# Don't scan documents larger than this for links — keeps a big workspace fast.
_MAX_SCAN_BYTES = 2 * 1024 * 1024


def _resolve_href(href: str, from_dir: str, doc_set: set):
    """Resolve one <a href> to a workspace-relative doc path, or None."""
    if not href:
        return None
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
        return None
    target = href
    try:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query) if parsed.query else {}
        # Phial's own routes carry the destination as ?path=...
        if qs.get("path"):
            target = qs["path"][0]
        else:
            target = parsed.path or href
    except Exception:  # noqa: BLE001
        target = href
    target = unquote(target).split("#")[0].strip().replace("\\", "/")
    if not target or not _DOC_EXT_RE.search(target):
        return None
    if target.startswith("/"):
        rel = posixpath.normpath(target.lstrip("/"))
    else:
        base = from_dir if from_dir not in ("", ".") else ""
        rel = posixpath.normpath(posixpath.join(base, target) if base else target)
    if rel in (".", "") or rel.startswith(".."):
        return None
    return rel if rel in doc_set else None


def _hrefs(html: str):
    try:
        soup = BeautifulSoup(html, "html.parser")
        return [a.get("href") or "" for a in soup.find_all("a")]
    except Exception:  # noqa: BLE001
        return re.findall(r'href=["\']([^"\']+)["\']', html)


# --- Markdown text layer -----------------------------------------------------

# Inline Markdown link: [label](target) — we only need the target.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")


def _md_link_targets(md_text: str, md_dir: str, doc_set: set):
    """Resolve the internal Markdown links of a text-layer page to doc paths.

    Links in `.phial/text/` point between `.md` files; map each one back to the
    matching workspace document (`.html`/`.htm`)."""
    out = []
    for m in _MD_LINK_RE.finditer(md_text):
        href = m.group(1).strip()
        if not href or href.startswith(("#", "http://", "https://", "mailto:", "tel:")):
            continue
        href = unquote(href.split("#")[0]).strip().replace("\\", "/")
        if not href.lower().endswith(".md"):
            continue
        if href.startswith("/"):
            rel = posixpath.normpath(href.lstrip("/"))
        else:
            rel = posixpath.normpath(posixpath.join(md_dir, href) if md_dir else href)
        if rel in (".", "") or rel.startswith(".."):
            continue
        stem = rel[:-3]  # drop ".md"
        for doc in (stem + ".html", stem + ".htm"):
            if doc in doc_set:
                out.append(doc)
                break
    return out


def build() -> dict:
    """Return {root, nodes, edges} for the active workspace."""
    root = Workspace.root()
    docs = Workspace.list_docs()
    doc_set = {d["path"] for d in docs}

    nodes = []
    for d in docs:
        rel = d["path"]
        nodes.append({
            "path": rel,
            "title": d.get("title") or d.get("name") or rel,
            "folder": posixpath.dirname(rel),
            "size": d.get("size", 0),
            "mtime": d.get("mtime"),
            "degree": 0,
        })

    edges = []
    seen = set()

    def add_edge(src: str, dst: str, kind: str):
        if src == dst or src not in doc_set or dst not in doc_set:
            return
        key = (src, dst, kind)
        if key in seen:
            return
        seen.add(key)
        edges.append({"source": src, "target": dst, "kind": kind})

    # --- link edges --------------------------------------------------------
    # Prefer the Markdown text layer (it reflects manual wiki edits); fall back
    # to scanning the document's own <a href> tags when it has no .md sidecar.
    from .doc_text import TEXT_DIR, _md_rel  # lazy: avoids an import cycle

    text_base = root / TEXT_DIR
    for d in docs:
        rel = d["path"]
        md_rel = _md_rel(rel)
        md_file = text_base / md_rel
        if md_file.is_file():
            try:
                md_text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                md_text = None
            if md_text is not None:
                for tgt in _md_link_targets(md_text, posixpath.dirname(md_rel), doc_set):
                    add_edge(rel, tgt, "link")
                continue
        # fallback: scan the HTML directly
        if d.get("size", 0) > _MAX_SCAN_BYTES:
            continue
        try:
            html = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        from_dir = posixpath.dirname(rel)
        for href in _hrefs(html):
            tgt = _resolve_href(href, from_dir, doc_set)
            if tgt:
                add_edge(rel, tgt, "link")

    # --- context edges: cross-document picks from the context picker -------
    ctx = app_settings.get("docContext")
    by_doc = ctx.get(str(root)) if isinstance(ctx, dict) else None
    if isinstance(by_doc, dict):
        for src, entry in by_doc.items():
            if not isinstance(entry, dict):
                continue
            for picked in entry.get("docs") or []:
                if isinstance(picked, str):
                    add_edge(src, picked.replace("\\", "/").strip().lstrip("/"), "context")

    deg = {n["path"]: 0 for n in nodes}
    for e in edges:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    for n in nodes:
        n["degree"] = deg.get(n["path"], 0)

    return {"root": str(root), "nodes": nodes, "edges": edges}
