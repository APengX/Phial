"""Convert an uploaded file into a Phial HTML document.

Single entry: `to_html_doc(filename, mime, raw_bytes)` -> (html_str, suggested_stem).
Supported sources:
  - PDF       -> pypdf text extraction, one <section> per page
  - Markdown  -> rendered to HTML
  - Plain text-> <pre>
  - HTML      -> normalized (kept as-is, doctype added)
  - Image     -> embedded as base64 <img>

Unsupported types raise MediaError so the route can return a clean 4xx.
Output is **always** a self-contained .html string, ready for write_doc().
"""

from __future__ import annotations

import base64
import html as _h
import io
import mimetypes
import re
from pathlib import PurePosixPath
from typing import Tuple

from ..utils.logger import get_logger

logger = get_logger("phial.media")


class MediaError(Exception):
    """Raised for unsupported types or unreadable input."""


_PDF_PLACEHOLDER_CSS = """
  body { font-family: -apple-system, "Segoe UI", "PingFang SC",
         "Microsoft YaHei", sans-serif;
         max-width: 560px; margin: 5rem auto; padding: 0 1.25rem; color: #1f2328; }
  .card { border: 1px solid #d0d7de; border-radius: 10px; padding: 2.5rem 2rem; text-align: center; }
  .icon { font-size: 3rem; margin-bottom: 1rem; }
  h1 { font-size: 1.4rem; margin: 0 0 0.4rem; word-break: break-all; }
  .meta { color: #6b7280; font-size: 0.875rem; margin-bottom: 1.5rem; }
  .hint { background: #f6f8fa; border-radius: 6px; padding: 0.9rem 1rem;
          font-size: 0.875rem; color: #374151; line-height: 1.6; }
""".strip()


def to_pdf_placeholder_doc(filename: str, stem: str, pdf_rel_path: str,
                            page_count: int = 0) -> str:
    """Lightweight placeholder HTML for a PDF kept as a native file.

    The meta tag `phial-pdf-src` lets ai.py detect this doc as a PDF reference
    and upload the file to the provider's Files API instead of text-extracting.
    """
    pages_note = f"· {page_count} 页 " if page_count else ""
    return (
        '<!DOCTYPE html>\n<html lang="zh">\n<head>\n'
        '  <meta charset="UTF-8">\n'
        f'  <meta name="phial-pdf-src" content="{_h.escape(pdf_rel_path)}">\n'
        f'  <title>{_h.escape(stem)}</title>\n'
        f'  <style>{_PDF_PLACEHOLDER_CSS}</style>\n'
        '</head>\n<body>\n'
        '  <div class="card">\n'
        '    <div class="icon">📄</div>\n'
        f'    <h1>{_h.escape(filename)}</h1>\n'
        f'    <p class="meta">PDF {pages_note}· 原始文件已保存至工作区</p>\n'
        '    <div class="hint">在右侧 AI 面板描述你想要的内容（总结、提取要点、问答等）'
        '，AI 将直接读取原始 PDF。</div>\n'
        '  </div>\n'
        '</body>\n</html>\n'
    )


_IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "image/svg+xml", "image/bmp", "image/avif",
}
_TEXT_MIMES = {"text/plain"}
_MD_EXTS = {".md", ".markdown", ".mdx"}
_TXT_EXTS = {".txt", ".log", ".csv", ".tsv"}
_HTML_EXTS = {".html", ".htm"}

# Generic CSS shared by all converters — kept inline so the doc stays
# fully self-contained (the iframe sandbox blocks external resources).
_BASE_CSS = """
  body { font-family: -apple-system, "Segoe UI", "PingFang SC",
         "Microsoft YaHei", sans-serif; max-width: 760px;
         margin: 2.5rem auto; padding: 0 1.25rem; line-height: 1.7;
         color: #1f2328; }
  h1, h2, h3 { line-height: 1.3; }
  h1 { font-size: 1.9rem; }
  pre { background: #f6f8fa; padding: 12px 14px; border-radius: 6px;
        overflow-x: auto; font-size: 13px; line-height: 1.55; }
  img { max-width: 100%; height: auto; }
  .page { padding: 1.25rem 0; border-bottom: 1px dashed #d0d7de; }
  .page:last-child { border-bottom: 0; }
  .page-tag { font-size: 11px; color: #6b7280; letter-spacing: 0.05em;
              text-transform: uppercase; }
  .src-tag { font-size: 12px; color: #6b7280; margin-bottom: 1.25rem; }
""".strip()


def to_html_doc(filename: str, mime: str, raw: bytes) -> Tuple[str, str]:
    """Return (html, suggested_stem). suggested_stem has no extension."""
    if not raw:
        raise MediaError("文件内容为空")

    name = (filename or "upload").strip() or "upload"
    stem = PurePosixPath(name).stem or "upload"
    suffix = PurePosixPath(name).suffix.lower()

    # Fill in mime from extension when the client didn't tag it (browsers
    # sometimes ship `application/octet-stream`).
    if not mime or mime == "application/octet-stream":
        guess, _ = mimetypes.guess_type(name)
        if guess:
            mime = guess
    mime = (mime or "").lower()

    if mime == "application/pdf" or suffix == ".pdf":
        return _from_pdf(raw, stem), stem
    if mime in _IMAGE_MIMES or suffix in {".png", ".jpg", ".jpeg", ".gif",
                                          ".webp", ".svg", ".bmp", ".avif"}:
        return _from_image(raw, name, mime or _guess_image_mime(suffix), stem), stem
    if suffix in _MD_EXTS or mime in {"text/markdown", "text/x-markdown"}:
        return _from_markdown(raw, stem), stem
    if suffix in _HTML_EXTS or mime in {"text/html", "application/xhtml+xml"}:
        return _from_html(raw, stem), stem
    if suffix in _TXT_EXTS or mime in _TEXT_MIMES or mime.startswith("text/"):
        return _from_text(raw, stem), stem

    raise MediaError(f"不支持的文件类型: {mime or suffix or 'unknown'}")


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------

def extract_pdf_text(raw: bytes, *, max_pages: int = 200) -> str:
    """Plain-text extraction for the fallback path when the provider's
    Files API isn't available. Returns "" on parse failure."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception:  # noqa: BLE001
        return ""
    out = []
    for i, page in enumerate(reader.pages, start=1):
        if i > max_pages:
            out.append(f"(... 截断，共 {len(reader.pages)} 页，仅展示前 {max_pages} 页)")
            break
        try:
            txt = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            txt = ""
        if txt.strip():
            out.append(f"--- 第 {i} 页 ---\n{txt.strip()}")
    return "\n\n".join(out)


def _from_pdf(raw: bytes, stem: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover — handled by deps
        raise MediaError("缺少 pypdf 依赖") from exc

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001 — pypdf raises a variety
        raise MediaError(f"PDF 解析失败: {exc}") from exc

    title = _pdf_title(reader, stem)
    pages_html = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            txt = ""
        body = _text_to_paragraphs(txt) or '<p class="muted">（这一页未抽取到文字）</p>'
        pages_html.append(
            f'<section class="page" aria-label="page {i}">'
            f'<div class="page-tag">第 {i} 页</div>{body}</section>'
        )
    src_note = (
        f'<p class="src-tag">来自 PDF · {_h.escape(stem)}.pdf · 共 '
        f"{len(reader.pages)} 页（仅抽取了文字，原始版式未保留）</p>"
    )
    return _wrap(title, src_note + "\n".join(pages_html))


def _pdf_title(reader, fallback: str) -> str:
    try:
        meta = reader.metadata or {}
        t = getattr(meta, "title", None) or meta.get("/Title")
        if t:
            return str(t).strip() or fallback
    except Exception:  # noqa: BLE001
        pass
    return fallback


def _from_image(raw: bytes, original_name: str, mime: str, stem: str) -> str:
    mime = mime or "application/octet-stream"
    b64 = base64.b64encode(raw).decode("ascii")
    src = f"data:{mime};base64,{b64}"
    alt = _h.escape(original_name)
    body = (
        f'<p class="src-tag">来自图片 · {alt}</p>\n'
        f'<p><img src="{src}" alt="{alt}"></p>'
    )
    return _wrap(stem, body)


def _from_markdown(raw: bytes, stem: str) -> str:
    text = _decode(raw)
    try:
        import markdown as _md
        body = _md.markdown(
            text,
            extensions=["fenced_code", "tables", "toc", "sane_lists"],
            output_format="html5",
        )
    except ImportError:
        body = f"<pre>{_h.escape(text)}</pre>"
    title = _first_h1(text) or stem
    return _wrap(title, body)


def _from_html(raw: bytes, stem: str) -> str:
    text = _decode(raw).strip()
    # Already a full doc? Keep it; just guarantee a doctype so the iframe
    # renders in standards mode.
    if re.search(r"<html[\s>]", text, re.IGNORECASE):
        if not text.lower().lstrip().startswith("<!doctype"):
            text = "<!DOCTYPE html>\n" + text
        return text
    return _wrap(stem, text)


def _from_text(raw: bytes, stem: str) -> str:
    text = _decode(raw)
    body = f"<pre>{_h.escape(text)}</pre>"
    return _wrap(stem, body)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _first_h1(md_text: str) -> str:
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""


def _text_to_paragraphs(text: str) -> str:
    """Convert raw extracted text into <p> blocks split on blank lines."""
    if not text.strip():
        return ""
    chunks = re.split(r"\n\s*\n+", text.strip())
    out = []
    for chunk in chunks:
        safe = _h.escape(chunk).replace("\n", "<br>")
        out.append(f"<p>{safe}</p>")
    return "\n".join(out)


def _guess_image_mime(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".bmp": "image/bmp",
        ".avif": "image/avif",
    }.get(suffix, "application/octet-stream")


def _wrap(title: str, body_html: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="zh">\n<head>\n'
        '  <meta charset="UTF-8">\n'
        f"  <title>{_h.escape(title)}</title>\n"
        f"  <style>{_BASE_CSS}</style>\n"
        f"</head>\n<body>\n  <h1>{_h.escape(title)}</h1>\n"
        f"  {body_html}\n</body>\n</html>\n"
    )
