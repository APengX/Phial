"""Per-document context API.

Folder bindings (HomeView):
  GET    /api/context/folders?path=<doc-rel>     -> {folders: [...]}
  GET    /api/context/folders/all                -> {byDoc: {<rel>: [...]}}
  POST   /api/context/folders   {path, folder}   -> {folders: [...]}
  DELETE /api/context/folders   {path, folder}   -> {folders: [...]}

Picker:
  GET    /api/context/picks?path=<doc-rel>       -> {folders, docs}
  PUT    /api/context/picks                      -> {folders, docs}
           body: {path, folders?, docs?}
  GET    /api/context/tree?path=&folder=         -> {files: [{rel, size}]}
  GET    /api/context/workspace-docs?path=       -> {docs:  [{rel, size, title}]}

A folder summary is `{path, name, fileCount, totalBytes, pickedCount, missing?}`
where `fileCount` is the *available* whitelisted file count under the folder
and `totalBytes` is the size of the *picked* subset (= what will be sent).
"""

from flask import request

from . import context_bp
from ..services import context_folder
from ..services.context_folder import ContextFolderError
from ..utils.logger import get_logger
from ..utils.responses import fail, ok

logger = get_logger("phial.api.context")


# ---------------------------------------------------------------------------
# Folder bindings (the "range" the picker draws from)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Picks (what actually goes into the prompt)
# ---------------------------------------------------------------------------

@context_bp.route("/picks", methods=["GET"])
def get_picks():
    doc_path = (request.args.get("path") or "").strip()
    if not doc_path:
        return fail("缺少 path")
    try:
        return ok(context_folder.get_picks(doc_path))
    except ContextFolderError as exc:
        return fail(str(exc))


@context_bp.route("/picks", methods=["PUT"])
def put_picks():
    data = request.get_json(silent=True) or {}
    doc_path = (data.get("path") or "").strip()
    if not doc_path:
        return fail("缺少 path")
    # `folders` / `docs` are independently optional — pass only the one you
    # want to update; the other stays untouched.
    folders = data.get("folders") if "folders" in data else None
    docs = data.get("docs") if "docs" in data else None
    try:
        return ok(context_folder.set_picks(doc_path, folders=folders, docs=docs))
    except ContextFolderError as exc:
        return fail(str(exc))


@context_bp.route("/tree", methods=["GET"])
def list_tree():
    """Enumerate pickable files inside one bound folder for the picker UI."""
    doc_path = (request.args.get("path") or "").strip()
    folder = (request.args.get("folder") or "").strip()
    if not doc_path:
        return fail("缺少 path")
    if not folder:
        return fail("缺少 folder")
    try:
        return ok({"files": context_folder.list_pickable(doc_path, folder)})
    except ContextFolderError as exc:
        return fail(str(exc))


@context_bp.route("/workspace-docs", methods=["GET"])
def list_workspace_docs():
    """All other `.html` docs in the workspace (for cross-doc picking).
    `path` (currently open doc) is excluded so users don't pick themselves."""
    exclude = (request.args.get("path") or "").strip() or None
    try:
        return ok({"docs": context_folder.list_workspace_docs(exclude=exclude)})
    except Exception:  # noqa: BLE001
        logger.exception("list_workspace_docs failed")
        return fail("无法枚举工作区文档", 500)
