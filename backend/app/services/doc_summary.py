"""AI-generated "30-second read" summaries for documents, with an on-disk cache.

The summary is host-side metadata — it is never written into the .html file, so
documents stay byte-stable and portable. The cache lives at
~/.phial/summaries.json, keyed by workspace + document path; a cached entry is
reused only while the document's content hash is unchanged.
"""

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup

from ..config import Config
from .workspace import Workspace

_FILE = Path(Config.APP_DATA_DIR) / "summaries.json"
_LOCK = threading.RLock()

# A summary doesn't need the whole document — cap the text we feed the model so
# a large doc doesn't blow the prompt budget.
_MAX_TEXT_CHARS = 12_000

_SYSTEM_PROMPT = """你是 Phial 的「30 秒速读」生成器。

用户给你一篇 HTML 文档的正文文字，请用 2-3 句话（中文约 60-120 字）概括：这篇文档讲的是什么、能用来做什么、读者最该先抓住的要点。目标是让人在 30 秒内对它有个判断。

要求：
- 只输出纯文本摘要，不要任何 HTML 标签或 Markdown 标记。
- 不要用「本文档 / 这篇文章」之类的废话开头，直接讲内容。
- 如果它其实是一个可操作的界面（看板、调参台、表单……），就说明它是干什么用的、怎么用。
- 文档是什么语言就用什么语言写摘要。"""

_USER_TEMPLATE = """文档标题：{title}

文档正文（已抽取为纯文字）：
{text}

请输出 2-3 句话的速读摘要。"""


def content_hash(html: str) -> str:
    return hashlib.sha1((html or "").encode("utf-8", "replace")).hexdigest()


def extract_text(html: str) -> str:
    """Strip a document down to readable text for the summary prompt."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        body = soup.body or soup
        text = body.get_text(separator="\n", strip=True)
    except Exception:  # noqa: BLE001
        text = html
    text = "\n".join(line for line in text.splitlines() if line.strip())
    return text[:_MAX_TEXT_CHARS]


def build_messages(html: str, title: str) -> List[dict]:
    text = extract_text(html)
    user = _USER_TEMPLATE.format(title=title or "(无标题)", text=text or "(空文档)")
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_prompt(html: str, title: str) -> str:
    """Flatten the messages into a single prompt string for CLI agents."""
    msgs = build_messages(html, title)
    return "\n\n---\n\n".join(m["content"].strip() for m in msgs)


# --- cache -------------------------------------------------------------------

def _read() -> dict:
    try:
        if _FILE.exists():
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write(data: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _root_key() -> str:
    return str(Workspace.root())


def get_cached(doc_rel: str, html: str) -> Optional[dict]:
    """Return {summary, ts, cached:true} when a fresh cached summary exists."""
    if not doc_rel:
        return None
    with _LOCK:
        by_doc = _read().get(_root_key()) or {}
    entry = by_doc.get(doc_rel)
    if not isinstance(entry, dict):
        return None
    if entry.get("hash") != content_hash(html):
        return None
    return {"summary": entry.get("summary", ""), "ts": entry.get("ts"), "cached": True}


def store(doc_rel: str, html: str, summary: str) -> dict:
    """Persist a freshly generated summary; returns the API-shaped result."""
    ts = datetime.now(timezone.utc).isoformat()
    if doc_rel:
        with _LOCK:
            data = _read()
            rk = _root_key()
            by_doc = dict(data.get(rk) or {})
            by_doc[doc_rel] = {"hash": content_hash(html), "summary": summary, "ts": ts}
            data[rk] = by_doc
            _write(data)
    return {"summary": summary, "ts": ts, "cached": False}
