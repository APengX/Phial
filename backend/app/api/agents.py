"""Agent selection API.

GET /api/agents            -> {detected:[...], builtin:{...}, current:{provider,model,env}, active:{...}}
PUT /api/agents            -> {provider, model?, env?}  pick the active provider
"""

from flask import request

from . import agents_bp
from ..services import agents as svc
from ..services import app_settings
from ..utils.logger import get_logger
from ..utils.responses import fail, ok

logger = get_logger("phial.api.agents")


@agents_bp.route("", methods=["GET"])
@agents_bp.route("/", methods=["GET"])
def list_agents():
    return ok(
        {
            "detected": svc.detect(),
            "builtin": {
                "id": svc.BUILTIN_ID,
                "name": "内置 LLM API",
                "configured": svc.builtin_ready(),
                "model": svc.builtin_model(),
            },
            "current": app_settings.get("agent"),
            "active": svc.active_summary(),
        }
    )


@agents_bp.route("", methods=["PUT"])
@agents_bp.route("/", methods=["PUT"])
def set_agent():
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or svc.BUILTIN_ID).strip()
    if provider != svc.BUILTIN_ID and svc.find(provider) is None:
        return fail(f"未知 agent: {provider}")

    patch = {"provider": provider}
    if "model" in data:
        patch["model"] = str(data.get("model") or "")
    if "env" in data:
        env = data.get("env") or {}
        if not isinstance(env, dict):
            return fail("env 必须是一个对象")
        patch["env"] = {str(k): str(v) for k, v in env.items() if str(k).strip()}

    settings = app_settings.update({"agent": patch})
    logger.info("active agent -> %s (model=%r)", provider, settings["agent"].get("model"))
    return ok({"current": settings["agent"], "active": svc.active_summary()})
