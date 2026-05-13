"""Registry + detection for local CLI coding agents (Claude Code, Codex, Gemini),
plus a summary of whichever provider is currently active.

The "builtin" provider is Phial's own OpenAI-compatible HTTP client (config via
.env). Any other provider id refers to a CLI in KNOWN_AGENTS that Phial shells
out to (see services/cli_agent.py).
"""

import shutil
import subprocess
from typing import Callable, List, Optional

from ..config import Config

BUILTIN_ID = "builtin"

# Each entry's "build" returns (argv, stdin_text_or_None): argv to exec, and the
# prompt text to feed on stdin (None -> the prompt is already in argv).
KNOWN_AGENTS = [
    {
        "id": "claude",
        "name": "Claude Code",
        "bin": "claude",
        "version_args": ["--version"],
        "default_model": "",
        "doc_url": "https://docs.anthropic.com/en/docs/claude-code",
        "model_label": "model（留空 = 用 Claude Code 的默认配置）",
        "env_hints": [
            {"key": "ANTHROPIC_API_KEY", "desc": "用 API key 调用时设置（已用订阅 /login 登录则不需要）"},
            {"key": "ANTHROPIC_BASE_URL", "desc": "自定义 API 网关"},
            {"key": "ANTHROPIC_MODEL", "desc": "默认模型"},
        ],
        "build": lambda model, prompt: (
            ["claude", "-p"] + (["--model", model] if model else []),
            prompt,  # fed via stdin
        ),
        "hint": lambda model: "claude -p" + (f" --model {model}" if model else "") + "  «prompt 经 stdin»",
    },
    {
        "id": "codex",
        "name": "Codex CLI (OpenAI)",
        "bin": "codex",
        "version_args": ["--version"],
        "default_model": "",
        "doc_url": "https://github.com/openai/codex",
        "model_label": "model",
        "env_hints": [
            {"key": "OPENAI_API_KEY", "desc": "OpenAI API key（也可用 codex login）"},
            {"key": "OPENAI_BASE_URL", "desc": "自定义 API 网关"},
        ],
        "build": lambda model, prompt: (
            ["codex", "exec"] + (["-m", model] if model else []) + [prompt],
            None,
        ),
        "hint": lambda model: "codex exec" + (f" -m {model}" if model else "") + ' "<prompt>"',
    },
    {
        "id": "gemini",
        "name": "Gemini CLI (Google)",
        "bin": "gemini",
        "version_args": ["--version"],
        "default_model": "",
        "doc_url": "https://github.com/google-gemini/gemini-cli",
        "model_label": "model",
        "env_hints": [
            {"key": "GEMINI_API_KEY", "desc": "Gemini API key"},
        ],
        "build": lambda model, prompt: (
            ["gemini"] + (["-m", model] if model else []) + ["-p", prompt],
            None,
        ),
        "hint": lambda model: "gemini" + (f" -m {model}" if model else "") + ' -p "<prompt>"',
    },
]

_BY_ID = {a["id"]: a for a in KNOWN_AGENTS}

# Env vars Phial is willing to forward into a CLI agent subprocess: only the keys
# we explicitly surface in env_hints. Anything else (NODE_OPTIONS, LD_PRELOAD,
# DYLD_*, PATH, ...) is dropped — those let a caller turn "set my API key" into
# arbitrary code execution in the child process.
ALLOWED_ENV_KEYS = frozenset(h["key"] for a in KNOWN_AGENTS for h in a["env_hints"])


def find(agent_id: str) -> Optional[dict]:
    return _BY_ID.get(agent_id)


def filter_env(env: Optional[dict]) -> dict:
    """Keep only allow-listed keys, coerced to str -> str."""
    return {str(k): str(v) for k, v in (env or {}).items() if str(k) in ALLOWED_ENV_KEYS}


def _probe_version(path: str, args: List[str]) -> Optional[str]:
    try:
        r = subprocess.run([path] + args, capture_output=True, text=True, timeout=4)
        text = (r.stdout or r.stderr or "").strip()
        return text.splitlines()[0].strip() if text else None
    except Exception:  # noqa: BLE001
        return None


def detect() -> List[dict]:
    """Probe PATH for each known CLI; include version when installed."""
    out = []
    for a in KNOWN_AGENTS:
        path = shutil.which(a["bin"])
        out.append(
            {
                "id": a["id"],
                "name": a["name"],
                "bin": a["bin"],
                "installed": path is not None,
                "path": path,
                "version": _probe_version(path, a["version_args"]) if path else None,
                "defaultModel": a["default_model"],
                "modelLabel": a["model_label"],
                "docUrl": a["doc_url"],
                "envHints": a["env_hints"],
            }
        )
    return out


def builtin_ready() -> bool:
    return Config.llm_configured()


def builtin_model() -> str:
    return Config.LLM_MODEL_NAME if Config.llm_configured() else ""


def active_summary() -> dict:
    """A small, display-oriented summary of the currently selected provider."""
    from . import app_settings  # local import to avoid an import cycle

    cfg = app_settings.get("agent") or {}
    provider = cfg.get("provider") or BUILTIN_ID
    model = cfg.get("model") or ""

    if provider == BUILTIN_ID:
        ready = builtin_ready()
        return {
            "provider": BUILTIN_ID,
            "name": "内置 LLM API",
            "model": builtin_model(),
            "installed": True,
            "ready": ready,
            "label": ("内置 API · " + builtin_model()) if ready else "内置 API（未配置 .env 中的 LLM_API_KEY）",
            "invocation": None,
        }

    a = find(provider)
    if not a:
        return {
            "provider": provider, "name": provider, "model": model, "installed": False,
            "ready": False, "label": f"未知 agent: {provider}", "invocation": None,
        }
    path = shutil.which(a["bin"])
    installed = path is not None
    eff_model = model or a["default_model"]
    argv, _ = a["build"](eff_model, "<prompt>")
    return {
        "provider": provider,
        "name": a["name"],
        "model": model,
        "installed": installed,
        "ready": installed,
        "label": f"{a['name']}（{a['bin']}）" + ("" if installed else " · 未安装"),
        "invocation": " ".join(argv) if installed else None,
    }
