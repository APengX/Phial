"""Keep the original uploaded file alongside each converted document.

When a file is uploaded, `media.to_html_doc()` converts it into a Phial
`.html` document — but that HTML is a *transformed* view (Markdown rendered,
PDF text reflowed, …) and the user may then edit it further with the AI
agent. The original wording can drift out of reach.

This module preserves the raw upload as a sidecar under `.phial/source/`,
mirroring the document tree the same way `.phial/text/` mirrors it:
`notes/plan.html` -> `.phial/source/notes/plan.md`. The chat layer feeds the
sidecar back in as context so the model interprets a picked element against
what the document actually said, instead of guessing from an HTML fragment.

PDFs uploaded through the native path are *not* mirrored here — they keep
their own `.pdf` file + `phial-pdf-src` meta and reach the model via the
provider's Files API. Images are skipped too (a sidecar of image bytes has
no textual value).
"""

import re
from pathlib import PurePosixPath
from typing import Optional

from ..utils.logger import get_logger
from .media import extract_pdf_text
from .workspace import Workspace

logger = get_logger("phial.doc_source")

# Folder (workspace-relative) that holds the preserved originals.
SOURCE_DIR = ".phial/source"

# Upper bound on how much of a source we splice into the prompt.
MAX_SOURCE_CHARS = 60_000

# Upload types worth preserving as a text-bearing sidecar. Images are
# deliberately absent — their content is the picture itself.
_KEEP_SUFFIXES = {
    ".md", ".markdown", ".mdx",
    ".txt", ".log", ".csv", ".tsv",
    ".html", ".htm",
    ".pdf",
}


# --- path helpers ------------------------------------------------------------

def _stem_rel(doc_rel: str) -> str:
    """`notes/plan.html` -> `notes/plan` (workspace-relative, no extension)."""
    return re.sub(r"\.html?$", "", doc_rel or "", flags=re.IGNORECASE)


def _should_keep(filename: str, mime: str) -> bool:
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix in _KEEP_SUFFIXES:
        return True
    mime = (mime or "").lower()
    if mime.startswith("image/"):
        return False
    return mime.startswith("text/") or mime in {
        "text/markdown", "text/x-markdown", "application/pdf",
        "application/xhtml+xml",
    }


def find_source(doc_rel: str) -> Optional[object]:
    """Absolute path of a document's preserved original, or None."""
    stem_rel = _stem_rel(doc_rel)
    if not stem_rel:
        return None
    base = Workspace.root() / SOURCE_DIR / stem_rel
    parent = base.parent
    if not parent.is_dir():
        return None
    for entry in sorted(parent.iterdir()):
        if entry.is_file() and entry.stem == base.name:
            return entry
    return None


# --- write / lifecycle -------------------------------------------------------

def save_source(doc_rel: str, original_filename: str, raw: bytes,
                 mime: str = "") -> Optional[object]:
    """Preserve an uploaded file as the sidecar for `doc_rel`.

    No-op (returns None) for empty input or non-text types (e.g. images).
    """
    if not raw or not _should_keep(original_filename, mime):
        return None
    stem_rel = _stem_rel(doc_rel)
    if not stem_rel:
        return None
    suffix = PurePosixPath(original_filename or "").suffix.lower() or ".txt"
    dest = Workspace.root() / SOURCE_DIR / (stem_rel + suffix)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    except OSError as exc:
        logger.warning("doc_source: save failed for %s: %s", doc_rel, exc)
        return None
    logger.info("doc_source: preserved original of %s -> %s", doc_rel, dest.name)
    return dest


def rename_source(src_rel: str, dst_rel: str) -> None:
    """Move a document's preserved original to follow a rename. Best-effort."""
    current = find_source(src_rel)
    if current is None:
        return
    dest = Workspace.root() / SOURCE_DIR / (_stem_rel(dst_rel) + current.suffix)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        current.rename(dest)
        logger.info("doc_source: moved %s -> %s", current.name, dest.name)
    except OSError as exc:
        logger.warning("doc_source: rename failed %s -> %s: %s", src_rel, dst_rel, exc)


def remove_source(rel: str) -> None:
    """Drop the preserved original(s) for a deleted document or folder.

    `rel` may name a single document or a whole folder; both branches are
    handled. Best-effort — a missing sidecar is not an error.
    """
    base = Workspace.root() / SOURCE_DIR / (rel or "").replace("\\", "/").strip("/")
    try:
        if base.is_dir():
            import shutil
            shutil.rmtree(base, ignore_errors=True)
            return
    except OSError:
        pass
    current = find_source(rel)
    if current is not None:
        try:
            current.unlink()
        except OSError:
            pass


# --- read --------------------------------------------------------------------

def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def source_text_for(doc_rel: str) -> str:
    """Return the preserved original of `doc_rel` as prompt-ready text.

    Empty string when there is no sidecar or it can't be read. PDFs are
    text-extracted; everything else is decoded as text. The result is capped
    at `MAX_SOURCE_CHARS` with a truncation marker.
    """
    src = find_source(doc_rel)
    if src is None:
        return ""
    try:
        raw = src.read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""

    if src.suffix.lower() == ".pdf":
        text = extract_pdf_text(raw)
    else:
        text = _decode(raw)
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS].rstrip() + "\n\n…（原稿过长，已截断）"
    return text
