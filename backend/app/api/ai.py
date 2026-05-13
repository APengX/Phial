"""AI endpoints: generate / edit a document's HTML (or interface).

Routes to whichever provider is active in settings:
  - "builtin": Phial's OpenAI-compatible HTTP client (LLM_* in .env)
  - a CLI id  : shells out to that local agent (Claude Code / Codex / Gemini)

POST /api/ai/chat   {prompt, currentHtml?, interfaceState?, path?}
  Streams Server-Sent Events:
    data: {"type":"delta","text":"..."}      (repeated)
    data: {"type":"done","html":"<full html>","raw":"<model reply>",
           "mode":"patch"|"full"|"noop","applied":N,"failed":["..."]}
    data: {"type":"error","message":"..."}
POST /api/ai/chat?stream=0   -> non-streaming, returns the same payload as JSON.

When editing an existing doc the model is asked for SEARCH/REPLACE blocks, which
the backend applies to `currentHtml` (see html_agent.finalize_html); it falls
back to treating the reply as a whole document if no blocks are found.
"""

import json

from flask import Response, request, stream_with_context

from . import ai_bp
from ..config import Config
from ..services import app_settings
from ..services import cli_agent
from ..services import context_folder
from ..services.agents import BUILTIN_ID
from ..services.cli_agent import CliAgentError
from ..services.html_agent import (
    build_chat_messages,
    build_chat_prompt,
    build_messages,
    build_prompt,
    finalize_html,
)
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
    path = data.get("path") or ""
    interface_state = data.get("interfaceState")
    if interface_state is None:
        interface_state = data.get("interface_state")
    picked_element = data.get("pickedElement") or data.get("picked_element")
    mode = (data.get("mode") or "agent").strip().lower()
    if mode not in ("agent", "chat"):
        mode = "agent"
    history = data.get("history") or []
    if not isinstance(history, list):
        history = []

    if not prompt and interface_state is None and not picked_element:
        return fail("缺少 prompt")

    agent_cfg = app_settings.get("agent") or {}
    provider = agent_cfg.get("provider") or BUILTIN_ID

    # Per-document context folders (set on the home page) get walked here
    # and dropped into the prompt as a "[背景资料]" system block. Empty
    # string when nothing is bound or the doc has no path yet.
    try:
        context_bundle = context_folder.bundle_for(path) if path else ""
    except Exception:  # noqa: BLE001
        logger.exception("context bundle build failed (non-fatal)")
        context_bundle = ""

    # Build a generator factory + a one-shot factory for the chosen provider.
    # Agent mode -> produce HTML edits; chat mode -> free-form text reply.
    if provider == BUILTIN_ID:
        try:
            client = LLMClient()
        except LLMNotConfigured as exc:
            return fail(str(exc), 503)
        if mode == "chat":
            messages = build_chat_messages(
                prompt, current_html, history, path, interface_state, picked_element,
                context_bundle=context_bundle,
            )
        else:
            messages = build_messages(
                prompt, current_html, interface_state, picked_element,
                context_bundle=context_bundle,
            )
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
        if mode == "chat":
            text_prompt = build_chat_prompt(
                prompt, current_html, history, path, interface_state, picked_element,
                context_bundle=context_bundle,
            )
        else:
            text_prompt = build_prompt(
                prompt, current_html, interface_state, picked_element,
                context_bundle=context_bundle,
            )
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
            if mode == "chat":
                return ok({"raw": raw, "mode": "chat", "text": raw})
            return ok({"raw": raw, **finalize_html(raw, current_html)})
        except CliAgentError as exc:
            logger.warning("CLI agent failed: %s", exc)
            return fail(str(exc), 502)
        except Exception:  # noqa: BLE001
            logger.exception("provider call failed")
            return fail("调用失败，请查看后端日志", 502)

    @stream_with_context
    def generate():
        buf = []
        try:
            for piece in make_stream():
                buf.append(piece)
                yield _sse({"type": "delta", "text": piece})
            raw = "".join(buf)
            if mode == "chat":
                yield _sse({"type": "done", "raw": raw, "mode": "chat", "text": raw})
            else:
                yield _sse({"type": "done", "raw": raw, **finalize_html(raw, current_html)})
        except CliAgentError as exc:
            logger.warning("CLI agent stream failed: %s", exc)
            yield _sse({"type": "error", "message": str(exc)})
        except Exception:  # noqa: BLE001
            logger.exception("provider stream failed")
            yield _sse({"type": "error", "message": "调用失败，请查看后端日志"})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
