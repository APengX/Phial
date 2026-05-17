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
import re
from pathlib import PurePosixPath

from flask import Response, request, stream_with_context

from . import ai_bp
from ..config import Config
from ..services import app_settings
from ..services import attachments as attachments_mod
from ..services import cli_agent
from ..services import context_folder
from ..services import media
from ..services.agents import BUILTIN_ID
from ..services.attachments import AttachmentsUnsupported
from ..services.cli_agent import CliAgentError
from ..services.html_agent import (
    build_chat_messages,
    build_chat_prompt,
    build_messages,
    build_prompt,
    finalize_html,
)
from ..services.llm_client import LLMClient, LLMNotConfigured
from ..services.workspace import Workspace, WorkspaceError
from ..utils.logger import get_logger
from ..utils.responses import fail, ok

_PDF_SRC_RE = re.compile(
    r'<meta[^>]+name="phial-pdf-src"[^>]+content="([^"]*)"',
    re.IGNORECASE,
)

logger = get_logger("phial.api.ai")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _pdf_text_block(picks) -> str:
    """Concatenate extracted PDF text for the fallback path. `picks` is the
    list of (path, label) from context_folder.attachments_for()."""
    chunks = []
    for fp, label in picks:
        try:
            raw = fp.read_bytes()
        except OSError as exc:
            logger.warning("PDF read failed (%s): %s", label, exc)
            continue
        text = media.extract_pdf_text(raw)
        if text:
            chunks.append(f"### {label} (PDF)\n{text}")
    if not chunks:
        return ""
    return "## PDF 附件（provider 不支持原生文件 → 已抽取为文字）\n\n" + "\n\n".join(chunks)


def _merge_bundle(bundle: str, extra: str) -> str:
    if not extra:
        return bundle
    if not bundle:
        return extra
    return bundle + "\n\n" + extra


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

    # PDF picks are routed to the provider's Files API when available;
    # otherwise we extract text and splice it into the bundle so the chat
    # still sees the document's contents.
    pdf_picks = []
    try:
        pdf_picks = context_folder.attachments_for(path) if path else []
    except Exception:  # noqa: BLE001
        logger.exception("attachments resolve failed (non-fatal)")
    attachments_blocks = []

    # If the current document is a PDF placeholder (uploaded via native path),
    # resolve its source file and prepend it to pdf_picks so it gets sent via
    # the inline file block, not text-extracted. Clear current_html so the
    # agent uses the CREATE template (the placeholder body isn't useful).
    doc_pdf_path = None
    m = _PDF_SRC_RE.search(current_html) if current_html else None
    if m:
        pdf_rel = m.group(1)
        logger.info("PDF placeholder detected: phial-pdf-src=%s", pdf_rel)
        try:
            doc_pdf_path = Workspace.resolve(pdf_rel, must_exist=True)
            pdf_picks = [(doc_pdf_path, PurePosixPath(pdf_rel).stem)] + pdf_picks
            current_html = ""
            logger.info("PDF resolved: %s", doc_pdf_path)
        except WorkspaceError as exc:
            logger.warning("PDF source file missing (%s): %s — sending placeholder as text", pdf_rel, exc)
    else:
        if current_html:
            logger.debug("no phial-pdf-src in current_html (len=%d)", len(current_html))

    # Build a generator factory + a one-shot factory for the chosen provider.
    # Agent mode -> produce HTML edits; chat mode -> free-form text reply.
    if provider == BUILTIN_ID:
        try:
            client = LLMClient()
        except LLMNotConfigured as exc:
            return fail(str(exc), 503)
        if pdf_picks:
            if attachments_mod.supports_file_blocks(client._client, client.model):
                logger.info("provider supports file blocks — building inline blocks for %d PDF(s)", len(pdf_picks))
                try:
                    attachments_blocks = attachments_mod.upload_pdfs(
                        client._client, pdf_picks, model=client.model
                    )
                    logger.info("PDF blocks built: %s", [b.get("type") for b in attachments_blocks])
                except AttachmentsUnsupported as exc:
                    logger.info("PDF files unreadable, falling back to text extraction: %s", exc)
                    context_bundle = _merge_bundle(context_bundle, _pdf_text_block(pdf_picks))
            else:
                logger.info("provider may strip file blocks (base_url=%s) — using text extraction", client.base_url)
                context_bundle = _merge_bundle(context_bundle, _pdf_text_block(pdf_picks))
        if mode == "chat":
            messages = build_chat_messages(
                prompt, current_html, history, path, interface_state, picked_element,
                context_bundle=context_bundle,
                attachments=attachments_blocks,
            )
        else:
            messages = build_messages(
                prompt, current_html, interface_state, picked_element,
                context_bundle=context_bundle,
                attachments=attachments_blocks,
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
        # CLI agents always go text-only — extract PDF text into the bundle.
        if pdf_picks:
            context_bundle = _merge_bundle(context_bundle, _pdf_text_block(pdf_picks))
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
