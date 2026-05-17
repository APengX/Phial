"""Inline-PDF content blocks for the AI layer.

`upload_pdfs(client, picks)` base64-encodes each PDF and returns a list of
content blocks suitable for the configured provider:

  Anthropic endpoints  →  {"type": "document", "source": {"type": "base64",
                            "media_type": "application/pdf", "data": "..."}}

  OpenAI / everything else  →  {"type": "file", "file": {
                                  "filename": "…", "file_data": "data:…;base64,…"}}

No Files-API upload, no file_id, no caching — the bytes go directly in the
request.  The `client` parameter (an openai.OpenAI instance) is read only for
its `base_url` so the right format is chosen; no network call is made here.

`AttachmentsUnsupported` is raised only when every supplied file is unreadable
on disk, allowing ai.py to fall back to pypdf text extraction.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterable, List, Tuple

from ..utils.logger import get_logger

logger = get_logger("phial.attachments")


class AttachmentsUnsupported(Exception):
    """Every PDF in the batch was unreadable; caller should fall back to
    text extraction."""


class AttachmentsError(Exception):
    """Kept for API compatibility; not currently raised."""


def supports_file_blocks(client, model: str) -> bool:
    """Return True only for providers known to forward file content blocks intact.

    Generic proxies (LiteLLM, custom gateways, etc.) silently drop `file` and
    `document` content blocks, so we conservatively return False for any URL
    that is not a recognised first-party endpoint.  Callers should fall back to
    text extraction when this returns False.
    """
    url = str(getattr(client, "base_url", "") or "").lower()
    if "api.anthropic.com" in url:
        return True
    if "api.openai.com" in url:
        return True
    if "openrouter.ai" in url:
        return True
    # Model-name heuristic for proxies that forward Claude under its real name
    return "claude" in model.lower()


def _use_anthropic_format(client, model: str) -> bool:
    """Return True when the provider expects Anthropic `document` blocks.

    Checks both base_url (direct Anthropic API) and model name (Claude models
    reached via LiteLLM, OpenRouter, or other proxies that forward the name).
    """
    url = str(getattr(client, "base_url", "") or "").lower()
    if "anthropic.com" in url:
        return True
    m = model.lower()
    return "claude" in m


def _make_block(fp: Path, b64: str, anthropic: bool) -> dict:
    if anthropic:
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": b64,
            },
        }
    return {
        "type": "file",
        "file": {
            "filename": fp.name,
            "file_data": f"data:application/pdf;base64,{b64}",
        },
    }


def upload_pdfs(client, picks: Iterable[Tuple[Path, str]], model: str = "") -> List[dict]:
    """Return inline content blocks for each (path, label) PDF.

    Unreadable files are skipped with a warning.  Raises
    `AttachmentsUnsupported` only when *every* file failed so ai.py can
    degrade to text extraction.
    """
    picks = list(picks)
    if not picks:
        return []

    anthropic = _use_anthropic_format(client, model)
    fmt = "document (Anthropic)" if anthropic else "file (OpenAI)"
    logger.info("PDF inline format: %s  base_url=%s  model=%s",
                fmt, getattr(client, "base_url", ""), model)

    blocks: List[dict] = []
    for fp, label in picks:
        try:
            b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
            blocks.append(_make_block(fp, b64, anthropic))
            logger.info("encoded PDF: %s (%d bytes → %d b64 chars)", fp.name, fp.stat().st_size, len(b64))
        except OSError as exc:
            logger.warning("PDF read failed (%s): %s", label, exc)

    if not blocks:
        raise AttachmentsUnsupported("所有 PDF 文件均无法读取")
    return blocks
