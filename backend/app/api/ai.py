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
from ..services import doc_source
from ..services import doc_summary
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


_HEAD_OPEN_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)


def _keep_pdf_src(result: dict, pdf_rel) -> dict:
    """Re-stamp the `phial-pdf-src` meta onto a freshly generated document.

    When the agent turns a PDF placeholder into real content it produces a
    brand-new HTML doc that no longer carries the meta — which would sever
    the link to the source PDF for every later chat / edit. This puts it
    back so the document stays anchored to its original."""
    if not pdf_rel:
        return result
    html = result.get("html") or ""
    if not html or _PDF_SRC_RE.search(html):
        return result
    safe = str(pdf_rel).replace("&", "&amp;").replace('"', "&quot;")
    meta = f'<meta name="phial-pdf-src" content="{safe}">'
    m = _HEAD_OPEN_RE.search(html)
    if m:
        result["html"] = html[: m.end()] + "\n  " + meta + html[m.end():]
    else:
        result["html"] = meta + "\n" + html
    return result


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

    # In chat mode the document's full text is otherwise withheld. If the doc
    # was created from an upload, feed its preserved original back in so the
    # model interprets a picked element against the real source, not a guess.
    source_text = ""
    if mode == "chat" and path:
        try:
            source_text = doc_source.source_text_for(path)
        except Exception:  # noqa: BLE001
            logger.exception("doc source lookup failed (non-fatal)")
            source_text = ""

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
    doc_pdf_rel = None  # set when the doc is linked to a still-present PDF
    m = _PDF_SRC_RE.search(current_html) if current_html else None
    if m:
        pdf_rel = m.group(1)
        logger.info("PDF placeholder detected: phial-pdf-src=%s", pdf_rel)
        try:
            doc_pdf_path = Workspace.resolve(pdf_rel, must_exist=True)
            doc_pdf_rel = pdf_rel
            pdf_picks = [(doc_pdf_path, PurePosixPath(pdf_rel).stem)] + pdf_picks
            current_html = ""
            logger.info("PDF resolved: %s", doc_pdf_path)
        except WorkspaceError as exc:
            logger.warning("PDF source file missing (%s): %s — sending placeholder as text", pdf_rel, exc)
    elif path:
        # Existing docs that lost the meta (AI regenerated them before this
        # fix, or they pre-date it): recover the link via the sibling PDF the
        # native upload leaves next to the doc (same dir, same stem, .pdf).
        # current_html is kept — these are real docs, not placeholders.
        sibling = re.sub(r"\.html?$", ".pdf", path, flags=re.IGNORECASE)
        if sibling != path:
            try:
                doc_pdf_path = Workspace.resolve(sibling, must_exist=True)
                doc_pdf_rel = sibling
                pdf_picks = [(doc_pdf_path, PurePosixPath(sibling).stem)] + pdf_picks
                logger.info("recovered sibling PDF for %s: %s", path, sibling)
            except WorkspaceError:
                pass

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
                source_text=source_text,
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
                source_text=source_text,
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
            return ok({"raw": raw, **_keep_pdf_src(finalize_html(raw, current_html), doc_pdf_rel)})
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
                yield _sse({"type": "done", "raw": raw, **_keep_pdf_src(finalize_html(raw, current_html), doc_pdf_rel)})
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


@ai_bp.route("/summary", methods=["POST"])
def summary():
    """Generate (or fetch the cached) "30-second read" summary for a document.

    Body: {path?, html, refresh?, peek?}
      - cache hit  -> returns the cached summary, no model call
      - peek=true  -> never calls the model; returns missing=true on a miss
      - refresh    -> regenerates even when a cached summary exists
    """
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "").strip()
    html = data.get("html") or data.get("currentHtml") or ""
    refresh = bool(data.get("refresh"))
    peek = bool(data.get("peek"))

    if not html.strip():
        return fail("文档为空，无法生成速读")

    if path and not refresh:
        cached = doc_summary.get_cached(path, html)
        if cached:
            return ok(cached)
    if peek:
        return ok({"summary": "", "cached": False, "missing": True})

    title = Workspace._title_from_html(html) or (
        path.rsplit("/", 1)[-1] if path else ""
    )

    agent_cfg = app_settings.get("agent") or {}
    provider = agent_cfg.get("provider") or BUILTIN_ID
    try:
        if provider == BUILTIN_ID:
            try:
                client = LLMClient()
            except LLMNotConfigured as exc:
                return fail(str(exc), 503)
            raw = client.chat(doc_summary.build_messages(html, title), max_tokens=400)
        else:
            try:
                cli_agent.ensure_available(provider)
            except CliAgentError as exc:
                return fail(str(exc), 503)
            raw = cli_agent.run(
                provider,
                doc_summary.build_prompt(html, title),
                model=agent_cfg.get("model") or "",
                env_extra=agent_cfg.get("env") or {},
            )
    except CliAgentError as exc:
        logger.warning("summary CLI agent failed: %s", exc)
        return fail(str(exc), 502)
    except Exception:  # noqa: BLE001
        logger.exception("summary generation failed")
        return fail("速读生成失败，请查看后端日志", 502)

    text = (raw or "").strip()
    if not text:
        return fail("模型没有返回内容", 502)
    return ok(doc_summary.store(path, html, text))
