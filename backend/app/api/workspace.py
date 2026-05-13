"""Workspace + render settings API.

GET  /api/workspace            -> {root, render, agent, llm_configured, model}
PUT  /api/workspace            -> {path}  switch the workspace root
GET  /api/workspace/render     -> render settings (sandbox / external resources)
PUT  /api/workspace/render     -> update render settings
"""

from flask import request

from . import workspace_bp
from ..config import Config
from ..services import agents as agents_svc
from ..services import app_settings
from ..services.workspace import Workspace, WorkspaceError
from ..utils.logger import get_logger
from ..utils.responses import fail, ok

logger = get_logger("phial.api.workspace")


def _render_settings() -> dict:
    return app_settings.get("render")


@workspace_bp.route("", methods=["GET"])
@workspace_bp.route("/", methods=["GET"])
def get_workspace():
    return ok(
        {
            "root": str(Workspace.root()),
            "render": _render_settings(),
            "agent": agents_svc.active_summary(),
            # kept for back-compat with earlier frontend builds
            "llm_configured": Config.llm_configured(),
            "model": Config.LLM_MODEL_NAME if Config.llm_configured() else None,
        }
    )


@workspace_bp.route("", methods=["PUT"])
@workspace_bp.route("/", methods=["PUT"])
def set_workspace():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    if not path:
        return fail("缺少 path")
    try:
        root = Workspace.set_root(path)
        return ok({"root": str(root)})
    except WorkspaceError as exc:
        return fail(str(exc))
    except OSError as exc:
        return fail(f"无法使用该文件夹: {exc}")


@workspace_bp.route("/render", methods=["GET"])
def get_render():
    return ok(_render_settings())


@workspace_bp.route("/render", methods=["PUT"])
def set_render():
    data = request.get_json(silent=True) or {}
    patch = {}
    if "allowScripts" in data:
        patch["allowScripts"] = bool(data["allowScripts"])
    if "allowExternal" in data:
        patch["allowExternal"] = bool(data["allowExternal"])
    settings = app_settings.update({"render": patch}) if patch else app_settings.load()
    return ok(settings["render"])
