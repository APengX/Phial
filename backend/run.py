"""Phial backend entry point."""

import os
import sys

# Make Windows consoles behave with UTF-8 before anything else imports.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    app = create_app()

    # Loopback by default: the API is unauthenticated, so don't expose it to the
    # LAN unless the user explicitly opts in via FLASK_HOST.
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", 5001))
    debug = Config.DEBUG

    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
