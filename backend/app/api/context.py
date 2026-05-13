"""Per-document context folders API.

GET    /api/context/folders?path=<doc-relpath>     -> {folders: [...]}
GET    /api/context/folders/all                    -> {byDoc: {<rel>: [...]}}
POST   /api/context/folders   {path, folder}       -> {folders: [...]}
DELETE /api/context/folders   {path, folder}       -> {folders: [...]}

A "folder" in the response is `{path, name, fileCount, totalBytes, missing?}`
where the numbers reflect what would be sent to the AI (whitelisted text
files only, after pruning .git / node_modules / etc.).
"""

from flask import request

from . import context_bp
from ..services import context_folder
from ..services.context_folder import ContextFolderError
from ..utils.logger import get_logger
from ..utils.responses import fail, ok

logger = get_logger("phial.api.context")


@context_bp.route("/folders", methods=["GET"])
def list_folders():
    doc_path = (request.args.get("path") or "").strip()
    if not doc_path:
        return fail("缺少 path")
    try:
        return ok({"folders": context_folder.list_for(doc_path)})
    except ContextFolderError as exc:
        return fail(str(exc))


@context_bp.route("/folders/all", methods=["GET"])
def list_all():
    """Bulk fetch for the home page so it can show a badge on every doc
    without an N+1 of single-doc requests."""
    try:
        return ok({"byDoc": context_folder.all_for_workspace()})
    except Exception:  # noqa: BLE001
        logger.exception("list_all failed")
        return fail("无法读取上下文设置", 500)


@context_bp.route("/folders", methods=["POST"])
def add_folder():
    data = request.get_json(silent=True) or {}
    doc_path = (data.get("path") or "").strip()
    folder = (data.get("folder") or "").strip()
    try:
        folders = context_folder.add_for(doc_path, folder)
        return ok({"folders": folders})
    except ContextFolderError as exc:
        return fail(str(exc))


@context_bp.route("/folders", methods=["DELETE"])
def remove_folder():
    # Accept either a JSON body or query string — `axios.delete` defaults to
    # query params unless you pass `{ data: ... }`, so support both.
    data = request.get_json(silent=True) or {}
    doc_path = (data.get("path") or request.args.get("path") or "").strip()
    folder = (data.get("folder") or request.args.get("folder") or "").strip()
    try:
        folders = context_folder.remove_for(doc_path, folder)
        return ok({"folders": folders})
    except ContextFolderError as exc:
        return fail(str(exc))
