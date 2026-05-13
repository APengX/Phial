"""Configuration loaded from the project-root .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Phial/backend/app/config.py -> Phial/.env
_PROJECT_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
if _PROJECT_ROOT_ENV.exists():
    load_dotenv(_PROJECT_ROOT_ENV, override=True)
else:
    load_dotenv(override=True)


def _default_workspace() -> str:
    return str(Path.home() / "PhialDocs")


class Config:
    """Flask + app configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "phial-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() == "true"

    # Show unicode (e.g. Chinese) directly in JSON responses.
    JSON_AS_ASCII = False

    # LLM (OpenAI-compatible)
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o")
    LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8192"))

    # Workspace: folder that holds the user's .html documents.
    # The runtime value can be overridden via the /api/workspace endpoint and is
    # persisted to ~/.phial/settings.json. This is just the bootstrap default.
    WORKSPACE_DEFAULT = os.environ.get("PHIAL_WORKSPACE") or _default_workspace()

    # Where Phial keeps its own small settings file.
    APP_DATA_DIR = str(Path.home() / ".phial")

    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB per document

    @classmethod
    def llm_configured(cls) -> bool:
        return bool(cls.LLM_API_KEY)
