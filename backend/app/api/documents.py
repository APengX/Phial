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

from flask import Response, request

from . import documents_bp
from ..services.workspace import Workspace, WorkspaceError
from ..utils.logger import get_logger
from ..utils.responses import fail, ok

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
