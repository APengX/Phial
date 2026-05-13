"""API blueprints."""

from flask import Blueprint

documents_bp = Blueprint("documents", __name__)
workspace_bp = Blueprint("workspace", __name__)
agents_bp = Blueprint("agents", __name__)
ai_bp = Blueprint("ai", __name__)
context_bp = Blueprint("context", __name__)

# Import route modules so they register on the blueprints above.
from . import documents  # noqa: E402,F401
from . import workspace  # noqa: E402,F401
from . import agents  # noqa: E402,F401
from . import ai  # noqa: E402,F401
from . import context  # noqa: E402,F401
