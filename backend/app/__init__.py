"""Phial backend - Flask application factory."""

import os

from flask import Flask
from flask_cors import CORS

from .config import Config
from .utils.logger import get_logger, setup_logger


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Emit unicode directly instead of \uXXXX.
    if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
        app.json.ensure_ascii = False

    logger = setup_logger("phial")

    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    should_log = (not app.config.get("DEBUG")) or is_reloader_child
    if should_log:
        logger.info("=" * 48)
        logger.info("Phial backend starting...")
        logger.info("workspace default: %s", config_class.WORKSPACE_DEFAULT)
        logger.info("CORS origins: %s", ", ".join(config_class.CORS_ORIGINS) or "(none)")
        logger.info("LLM configured: %s", config_class.llm_configured())
        logger.info("=" * 48)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from .api import agents_bp, ai_bp, context_bp, documents_bp, workspace_bp

    app.register_blueprint(documents_bp, url_prefix="/api/documents")
    app.register_blueprint(workspace_bp, url_prefix="/api/workspace")
    app.register_blueprint(agents_bp, url_prefix="/api/agents")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")
    app.register_blueprint(context_bp, url_prefix="/api/context")

    @app.route("/health")
    def health():
        return {"status": "ok", "service": "Phial backend"}

    # Drop the agent bundle (AGENTS.md + CLAUDE.md + the phial-html skill)
    # into the active workspace so external agents that later crawl or load
    # the folder know to emit Phial-flavoured HTML. Write-once per file;
    # see services/agent_guide.py for the policy. Failure is non-fatal —
    # the server can still run without it.
    try:
        from .services import agent_guide
        from .services.workspace import Workspace

        agent_guide.ensure(Workspace.root())
    except Exception:  # noqa: BLE001
        logger.exception("agent guide ensure failed (non-fatal)")

    if should_log:
        logger.info("Phial backend ready.")
    return app
