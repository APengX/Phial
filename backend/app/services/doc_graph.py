"""Build a document relationship graph for the active workspace.

Nodes are .html documents. Edges come from two sources:
  - "link"    : an <a href> in one document that resolves to another doc
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

    # --- link edges: <a href> pointing at another workspace doc ------------
    for d in docs:
        rel = d["path"]
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
