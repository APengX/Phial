"""REST API for documents in the active workspace.

GET    /api/documents/tree            -> folder tree
GET    /api/documents/list            -> flat list (recent first)
GET    /api/documents/content?path=   -> one document {path,title,html,...}
POST   /api/documents                 -> create   {path, html?, title?}
PUT    /api/documents/content         -> save     {path, html}
POST   /api/documents/rename          -> rename   {src, dst}
DELETE /api/documents?path=           -> delete   (a document, or a folder + its contents)
POST   /api/documents/mkdir           -> create folder {path}
"""

import io

from flask import Response, request

from . import documents_bp
from ..services import app_settings, auto_link, cli_agent, doc_graph, doc_text
from ..services.agents import BUILTIN_ID
from ..services.cli_agent import CliAgentError
from ..services.llm_client import LLMClient, LLMNotConfigured
from ..services.media import MediaError, to_html_doc, to_pdf_placeholder_doc
from ..services.workspace import Workspace, WorkspaceError
from ..utils.logger import get_logger
from ..utils.responses import fail, ok


def _count_pdf_pages(raw: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(raw)).pages)
    except Exception:  # noqa: BLE001
        return 0

logger = get_logger("phial.api.documents")


def _body() -> dict:
    return request.get_json(silent=True) or {}


@documents_bp.route("/tree", methods=["GET"])
def tree():
    try:
        return ok(Workspace.tree())
    except WorkspaceError as exc:
        return fail(str(exc))


@documents_bp.route("/list", methods=["GET"])
def list_docs():
    try:
        return ok({"documents": Workspace.list_docs()})
    except WorkspaceError as exc:
        return fail(str(exc))


@documents_bp.route("/graph", methods=["GET"])
def graph():
    """Document relationship graph (nodes = docs, edges = links + context)."""
    try:
        return ok(doc_graph.build())
    except WorkspaceError as exc:
        return fail(str(exc))


@documents_bp.route("/extract-text", methods=["POST"])
def extract_text():
    """Extract documents into the Markdown text layer under `.phial/text/`.

    Body: optional {path} to extract a single document; absent extracts the
    whole workspace. Returns {count, files, dir}."""
    path = (_body().get("path") or "").strip()
    try:
        return ok(doc_text.extract_one(path) if path else doc_text.extract_all())
    except WorkspaceError as exc:
        return fail(str(exc), 404 if "不存在" in str(exc) else 400)


def _auto_link_ai(html: str, targets: list) -> list:
    """Run the AI fuzzy-match pass through whichever provider is active.

    Best-effort: any provider failure returns [] so the exact-match pass still
    yields candidates."""
    agent_cfg = app_settings.get("agent") or {}
    provider = agent_cfg.get("provider") or BUILTIN_ID
    try:
        if provider == BUILTIN_ID:
            try:
                client = LLMClient()
            except LLMNotConfigured:
                return []
            raw = client.chat(auto_link.build_messages(html, targets), max_tokens=1500)
        else:
            try:
                cli_agent.ensure_available(provider)
            except CliAgentError:
                return []
            raw = cli_agent.run(
                provider,
                auto_link.build_prompt(html, targets),
                model=agent_cfg.get("model") or "",
                env_extra=agent_cfg.get("env") or {},
            )
    except Exception:  # noqa: BLE001
        logger.exception("auto-link AI pass failed (non-fatal)")
        return []
    return auto_link.parse_ai(raw, html, targets)


@documents_bp.route("/auto-link/scan", methods=["POST"])
def auto_link_scan():
    """Find words in a document that name other workspace documents.

    Body: {path, html}. Returns {candidates:[{id,phrase,target,title,kind,
    snippet}], aiUsed}. Exact title matches first, then an AI fuzzy pass over
    whatever wasn't matched."""
    data = _body()
    path = (data.get("path") or "").strip()
    html = data.get("html") or ""
    if not html.strip():
        return fail("文档为空，无法扫描")
    try:
        targets = auto_link.collect_targets(path)
    except WorkspaceError as exc:
        return fail(str(exc))
    if not targets:
        return ok({"candidates": [], "aiUsed": False})

    exact = auto_link.exact_candidates(html, targets)
    linked = {c["target"] for c in exact}
    remaining = [t for t in targets if t["path"] not in linked]
    ai = _auto_link_ai(html, remaining) if remaining else []

    candidates = exact + ai
    for i, c in enumerate(candidates):
        c["id"] = i
    return ok({"candidates": candidates, "aiUsed": bool(remaining)})


@documents_bp.route("/auto-link/apply", methods=["POST"])
def auto_link_apply():
    """Wrap the chosen phrases in links. Body: {path, html, picks:[{phrase,
    target}]}. Returns {html, applied}."""
    data = _body()
    path = (data.get("path") or "").strip()
    html = data.get("html") or ""
    picks = data.get("picks") or []
    if not html.strip():
        return fail("文档为空")
    if not isinstance(picks, list) or not picks:
        return fail("没有选择要添加的链接")
    new_html, applied = auto_link.apply_links(path, html, picks)
    return ok({"html": new_html, "applied": applied})


@documents_bp.route("/auto-link/scan-all", methods=["POST"])
def auto_link_scan_all():
    """Workspace-wide auto-link: exact-title matches across every document.

    Refreshes the Markdown text layer first, then matches against it (links are
    still applied as <a href> in the HTML). Returns {groups:[{path,title,
    candidates:[...]}]}. Exact-only — no model calls."""
    try:
        try:
            doc_text.extract_all()
        except Exception:  # noqa: BLE001
            logger.exception("auto-link scan-all: text extraction failed (non-fatal)")
        groups = auto_link.scan_workspace()
    except WorkspaceError as exc:
        return fail(str(exc))
    return ok({"groups": groups})


@documents_bp.route("/auto-link/apply-all", methods=["POST"])
def auto_link_apply_all():
    """Apply chosen links across multiple documents and save each to disk.

    Body: {groups:[{path, picks:[{phrase,target}]}]}. Returns {applied, docs}."""
    groups = _body().get("groups") or []
    if not isinstance(groups, list) or not groups:
        return fail("没有选择要添加的链接")
    total = 0
    docs_changed = 0
    for g in groups:
        if not isinstance(g, dict):
            continue
        path = (g.get("path") or "").strip()
        picks = g.get("picks") or []
        if not path or not isinstance(picks, list) or not picks:
            continue
        try:
            html = Workspace.read_doc(path)["html"]
        except WorkspaceError:
            logger.warning("auto-link apply-all: skipping missing doc %s", path)
            continue
        new_html, applied = auto_link.apply_links(path, html, picks)
        if applied:
            try:
                Workspace.write_doc(path, new_html)
            except WorkspaceError as exc:
                logger.warning("auto-link apply-all: write failed %s: %s", path, exc)
                continue
            total += applied
            docs_changed += 1
    logger.info("auto-link apply-all: %d links across %d docs", total, docs_changed)
    return ok({"applied": total, "docs": docs_changed})


@documents_bp.route("/content", methods=["GET"])
def get_content():
    path = request.args.get("path", "")
    try:
        return ok(Workspace.read_doc(path))
    except WorkspaceError as exc:
        return fail(str(exc), 404 if "不存在" in str(exc) else 400)


@documents_bp.route("/raw", methods=["GET"])
def raw_content():
    """Serve a document as text/html so it can be opened directly in a browser
    tab (unsandboxed - this is the "open in browser" escape hatch)."""
    path = request.args.get("path", "")
    try:
        doc = Workspace.read_doc(path)
    except WorkspaceError as exc:
        return fail(str(exc), 404 if "不存在" in str(exc) else 400)
    return Response(doc["html"], mimetype="text/html; charset=utf-8")


@documents_bp.route("", methods=["POST"])
@documents_bp.route("/", methods=["POST"])
def create_doc():
    data = _body()
    path = data.get("path", "")
    try:
        doc = Workspace.create_doc(path, html=data.get("html"), title=data.get("title"))
        logger.info("created document %s", doc["path"])
        return ok(doc, 201)
    except WorkspaceError as exc:
        return fail(str(exc), 409 if "已存在" in str(exc) else 400)


@documents_bp.route("/content", methods=["PUT"])
def save_content():
    data = _body()
    path = data.get("path", "")
    html = data.get("html")
    if html is None:
        return fail("缺少 html 内容")
    try:
        return ok(Workspace.write_doc(path, html))
    except WorkspaceError as exc:
        return fail(str(exc))


@documents_bp.route("/rename", methods=["POST"])
def rename_doc():
    data = _body()
    try:
        return ok(Workspace.rename_doc(data.get("src", ""), data.get("dst", "")))
    except WorkspaceError as exc:
        return fail(str(exc), 409 if "已存在" in str(exc) else 400)


@documents_bp.route("", methods=["DELETE"])
@documents_bp.route("/", methods=["DELETE"])
def delete_doc():
    path = request.args.get("path", "") or _body().get("path", "")
    try:
        Workspace.delete_doc(path)
        logger.info("deleted %s", path)
        return ok({"path": path})
    except WorkspaceError as exc:
        return fail(str(exc), 404 if "不存在" in str(exc) else 400)
    except OSError as exc:
        return fail(f"删除失败: {exc}")


@documents_bp.route("/mkdir", methods=["POST"])
def mkdir():
    path = _body().get("path", "")
    try:
        Workspace.mkdir(path)
        return ok({"path": path})
    except WorkspaceError as exc:
        return fail(str(exc))


@documents_bp.route("/upload", methods=["POST"])
def upload_doc():
    """Convert an uploaded file (PDF / MD / TXT / HTML / image) into a new
    workspace document. multipart/form-data; field name: `file`. Optional
    `dir` (workspace-relative) places the new doc in a subfolder.

    PDFs are stored as-is (`.pdf` in the workspace) and the Phial document
    becomes a lightweight placeholder that points to the file. The AI layer
    picks up the `phial-pdf-src` meta tag and forwards the raw PDF to the
    provider via the Files API instead of extracting text.
    """
    if "file" not in request.files:
        return fail("缺少 file 字段")
    f = request.files["file"]
    if not f.filename:
        return fail("缺少文件名")
    raw = f.read()
    if not raw:
        return fail("文件内容为空")

    mime = (f.mimetype or "").lower()
    if not mime or mime == "application/octet-stream":
        import mimetypes as _mt
        guess, _ = _mt.guess_type(f.filename)
        if guess:
            mime = guess.lower()

    from pathlib import PurePosixPath as _P
    stem = _P(f.filename).stem or "upload"
    suffix = _P(f.filename).suffix.lower()

    dir_rel = (request.form.get("dir") or "").strip().replace("\\", "/").strip("/")
    prefix = f"{dir_rel}/" if dir_rel else ""

    # PDFs: keep original file, create a placeholder doc with phial-pdf-src
    if mime == "application/pdf" or suffix == ".pdf":
        try:
            page_count = _count_pdf_pages(raw)
            html_rel = Workspace.unique_doc_path(prefix + stem)
            pdf_rel = html_rel[:-5] + ".pdf"  # sibling file: same stem, .pdf ext
            Workspace.write_file(pdf_rel, raw)
            placeholder = to_pdf_placeholder_doc(f.filename, stem, pdf_rel, page_count)
            doc = Workspace.create_doc(html_rel, html=placeholder)
            logger.info("uploaded PDF (native) %s -> html=%s pdf=%s", f.filename, doc["path"], pdf_rel)
            return ok(doc, 201)
        except WorkspaceError as exc:
            return fail(str(exc), 409 if "已存在" in str(exc) else 400)
        except Exception:  # noqa: BLE001
            logger.exception("PDF native save failed, falling back to text extraction")

    # All other types (and PDF fallback): convert to an HTML document
    try:
        html, stem = to_html_doc(f.filename, mime, raw)
    except MediaError as exc:
        return fail(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("upload conversion failed")
        return fail("文件转换失败", 500)

    try:
        rel = Workspace.unique_doc_path(prefix + stem)
        doc = Workspace.create_doc(rel, html=html)
        logger.info("uploaded %s -> %s", f.filename, doc["path"])
        return ok(doc, 201)
    except WorkspaceError as exc:
        return fail(str(exc), 409 if "已存在" in str(exc) else 400)
