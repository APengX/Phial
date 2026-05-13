"""Single source of truth for Phial's persisted settings (~/.phial/settings.json).

Schema (all keys optional in the file; defaults fill the rest):
  {
    "workspace": "/abs/path" | null,                # null -> Config.WORKSPACE_DEFAULT
    "render":   {"allowScripts": bool, "allowExternal": bool},
    "agent":    {"provider": "builtin"|"<cli-id>", "model": str, "env": {KEY: VAL}}
  }
"""

import json
import threading
from pathlib import Path

from ..config import Config

_FILE = Path(Config.APP_DATA_DIR) / "settings.json"
_LOCK = threading.RLock()

DEFAULTS = {
    "workspace": None,
    "render": {"allowScripts": True, "allowExternal": False},
    "agent": {"provider": "builtin", "model": "", "env": {}},
}


def _read_raw() -> dict:
    try:
        if _FILE.exists():
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_raw(data: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> dict:
    """Return the full settings dict with defaults merged in (one level deep)."""
    with _LOCK:
        raw = _read_raw()
    out = {}
    for key, default in DEFAULTS.items():
        if isinstance(default, dict):
            got = raw.get(key)
            out[key] = {**default, **(got if isinstance(got, dict) else {})}
        else:
            out[key] = raw.get(key, default)
    # keep any unknown keys too, just in case
    for key, val in raw.items():
        if key not in out:
            out[key] = val
    return out


def get(key: str, default=None):
    return load().get(key, default)


def update(patch: dict) -> dict:
    """Shallow-merge `patch` into the file (dict values merge one level deep)
    and return the resulting full settings (with defaults)."""
    with _LOCK:
        raw = _read_raw()
        for key, val in patch.items():
            if isinstance(val, dict) and isinstance(raw.get(key), dict):
                raw[key] = {**raw[key], **val}
            else:
                raw[key] = val
        _write_raw(raw)
    return load()


def set_key(key: str, value) -> dict:
    with _LOCK:
        raw = _read_raw()
        raw[key] = value
        _write_raw(raw)
    return load()
