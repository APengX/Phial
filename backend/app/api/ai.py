"""AI endpoints: generate / edit a document's HTML (or interface).

Routes to whichever provider is active in settings:
  - "builtin": Phial's OpenAI-compatible HTTP client (LLM_* in .env)
  - a CLI id  : shells out to that local agent (Claude Code / Codex / Gemini)

POST /api/ai/chat   {prompt, currentHtml?, interfaceState?, path?}
  Streams Server-Sent Events:
    data: {"type":"delta","text":"..."}      (repeated)
    data: {"type":"done","html":"<full html>","raw":"<model reply>"}
    data: {"type":"error","message":"..."}
POST /api/ai/chat?stream=0   -> non-streaming, returns {html, raw} as plain JSON.
"""

import json

from flask import Response, request, stream_with_context

from . import ai_bp
from ..config import Config
from ..services import app_settings
from ..services import cli_agent
from ..services.agents import BUILTIN_ID
from ..services.cli_agent import CliAgentError
from ..services.html_agent import build_messages, build_prompt, extract_html
from ..services.llm_client import LLMClient, LLMNotConfigured
from ..utils.logger import get_logger
from ..utils.responses import fail, ok

logger = get_logger("phial.api.ai")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@ai_bp.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    current_html = data.get("currentHtml") or data.get("current_html") or ""
    interface_state = data.get("interfaceState")
    if interface_state is None:
        interface_state = data.get("interface_state")
    if not prompt and interface_state is None:
        return fail("缺少 prompt")

    agent_cfg = app_settings.get("agent") or {}
    provider = agent_cfg.get("provider") or BUILTIN_ID

    # Build a generator factory + a one-shot factory for the chosen provider.
    if provider == BUILTIN_ID:
        try:
            client = LLMClient()
        except LLMNotConfigured as exc:
            return fail(str(exc), 503)
        messages = build_messages(prompt, current_html, interface_state)
        max_tokens = Config.LLM_MAX_TOKENS

        def make_stream():
            return client.stream(messages, max_tokens=max_tokens)

        def make_oneshot():
            return client.chat(messages, max_tokens=max_tokens)

    else:
        try:
            cli_agent.ensure_available(provider)
        except CliAgentError as exc:
            return fail(str(exc), 503)
        text_prompt = build_prompt(prompt, current_html, interface_state)
        model = agent_cfg.get("model") or ""
        env_extra = agent_cfg.get("env") or {}

        def make_stream():
            return cli_agent.stream(provider, text_prompt, model=model, env_extra=env_extra)

        def make_oneshot():
            return cli_agent.run(provider, text_prompt, model=model, env_extra=env_extra)

    streaming = request.args.get("stream", "1") not in ("0", "false", "no")

    if not streaming:
        try:
            raw = make_oneshot()
            return ok({"raw": raw, "html": extract_html(raw)})
        except CliAgentError as exc:
            logger.warning("CLI agent failed: %s", exc)
            return fail(str(exc), 502)
        except Exception as exc:  # noqa: BLE001
            logger.exception("provider call failed")
            return fail(f"调用失败: {exc}", 502)

    @stream_with_context
    def generate():
        buf = []
        try:
            for piece in make_stream():
                buf.append(piece)
                yield _sse({"type": "delta", "text": piece})
            raw = "".join(buf)
            yield _sse({"type": "done", "raw": raw, "html": extract_html(raw)})
        except CliAgentError as exc:
            logger.warning("CLI agent stream failed: %s", exc)
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("provider stream failed")
            yield _sse({"type": "error", "message": f"调用失败: {exc}"})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
