"""Workspace = a local folder of .html documents.

One document == one .html file. Folders nest freely. The workspace root can be
changed at runtime and is persisted to ~/.phial/settings.json.
"""

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from ..config import Config
from ..utils.logger import get_logger
from . import agent_guide, app_settings

logger = get_logger("phial.workspace")

DOC_SUFFIXES = {".html", ".htm"}

DEFAULT_DOC_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
           max-width: 760px; margin: 3rem auto; padding: 0 1.25rem; line-height: 1.7; color: #1f2328; }}
    h1 {{ font-size: 1.9rem; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>开始写作，或在右侧 AI 面板里描述你想要的内容。</p>
</body>
</html>
"""


class WorkspaceError(Exception):
    """Raised for invalid paths / IO problems the API should turn into 4xx."""


class Workspace:
    """Singleton-ish accessor for the active workspace root."""

    _root: Optional[Path] = None

    # -- root management ----------------------------------------------------
    @classmethod
    def root(cls) -> Path:
        if cls._root is None:
            saved = app_settings.get("workspace")
            base = Path(saved).expanduser() if saved else Path(Config.WORKSPACE_DEFAULT).expanduser()
            cls._root = base
        cls._root.mkdir(parents=True, exist_ok=True)
        # Resolve so symlinked roots (e.g. /tmp -> /private/tmp on macOS) stay
        # consistent with resolved document paths.
        return cls._root.resolve()

    @classmethod
    def set_root(cls, new_path: str) -> Path:
        p = Path(new_path).expanduser()
        if p.exists() and not p.is_dir():
            raise WorkspaceError(f"{p} 不是文件夹")
        p.mkdir(parents=True, exist_ok=True)
        p = p.resolve()
        cls._root = p
        app_settings.set_key("workspace", str(p))
        logger.info("workspace root set to %s", p)
        # First time we point at a folder, drop the agent bundle (AGENTS.md
        # + CLAUDE.md + the phial-html skill) so external agents that crawl
        # or load it later know what Phial expects (see agent_guide).
        agent_guide.ensure(p)
        return p

    # -- path safety --------------------------------------------------------
    @classmethod
    def resolve(cls, rel_path: str, *, must_exist: bool = False) -> Path:
        """Resolve a workspace-relative path, refusing anything outside the root."""
        if rel_path is None or rel_path == "":
            raise WorkspaceError("缺少文档路径")
        rel = rel_path.replace("\\", "/").lstrip("/")
        if ".." in Path(rel).parts:
            raise WorkspaceError("非法路径")
        root = cls.root().resolve()
        target = (root / rel).resolve()
        if target != root and root not in target.parents:
            raise WorkspaceError("非法路径")
        if must_exist and not target.exists():
            raise WorkspaceError("文档不存在")
        return target

    # -- listing ------------------------------------------------------------
    @classmethod
    def tree(cls) -> dict:
        root = cls.root()
        return {
            "root": str(root),
            "name": root.name or str(root),
            "children": cls._scan_dir(root, root),
        }

    @classmethod
    def _scan_dir(cls, directory: Path, root: Path) -> list:
        items = []
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except OSError:
            return items
        for entry in entries:
            if entry.name.startswith("."):
                continue
            rel = entry.relative_to(root).as_posix()
            if entry.is_dir():
                children = cls._scan_dir(entry, root)
                items.append({"type": "dir", "name": entry.name, "path": rel, "children": children})
            elif entry.suffix.lower() in DOC_SUFFIXES:
                items.append(
                    {
                        "type": "doc",
                        "name": entry.name,
                        "path": rel,
                        "title": cls._title_of(entry),
                        "mtime": _iso(entry.stat().st_mtime),
                        "size": entry.stat().st_size,
                    }
                )
        return items

    @classmethod
    def list_docs(cls) -> list:
        """Flat list of all documents (handy for search / recent)."""
        out: list = []

        def walk(node: dict):
            for child in node.get("children", []):
                if child["type"] == "doc":
                    out.append(child)
                else:
                    walk(child)

        walk(cls.tree())
        out.sort(key=lambda d: d["mtime"], reverse=True)
        return out

    # -- document IO --------------------------------------------------------
    @classmethod
    def read_doc(cls, rel_path: str) -> dict:
        target = cls.resolve(rel_path, must_exist=True)
        if target.suffix.lower() not in DOC_SUFFIXES:
            raise WorkspaceError("不是 HTML 文档")
        html = target.read_text(encoding="utf-8", errors="replace")
        st = target.stat()
        return {
            "path": target.relative_to(cls.root()).as_posix(),
            "name": target.name,
            "title": cls._title_from_html(html) or target.stem,
            "html": html,
            "mtime": _iso(st.st_mtime),
            "size": st.st_size,
        }

    @classmethod
    def write_doc(cls, rel_path: str, html: str) -> dict:
        target = cls.resolve(rel_path)
        if target.suffix.lower() not in DOC_SUFFIXES:
            raise WorkspaceError("文档名必须以 .html 结尾")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html if html is not None else "", encoding="utf-8")
        return cls.read_doc(target.relative_to(cls.root()).as_posix())

    @classmethod
    def create_doc(cls, rel_path: str, html: Optional[str] = None, title: Optional[str] = None) -> dict:
        target = cls.resolve(rel_path)
        if target.suffix.lower() not in DOC_SUFFIXES:
            # allow callers to omit the extension
            target = target.with_suffix(".html")
            rel_path = target.relative_to(cls.root()).as_posix()
        if target.exists():
            raise WorkspaceError("同名文档已存在")
        if html is None:
            html = DEFAULT_DOC_HTML.format(title=_escape(title or target.stem))
        return cls.write_doc(rel_path, html)

    @classmethod
    def delete_doc(cls, rel_path: str) -> None:
        """Delete a document, or a folder and everything inside it."""
        target = cls.resolve(rel_path, must_exist=True)
        if target == cls.root():
            raise WorkspaceError("不能删除工作区根目录")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    @classmethod
    def rename_doc(cls, src: str, dst: str) -> dict:
        src_p = cls.resolve(src, must_exist=True)
        if src_p.is_dir():
            raise WorkspaceError("不能用此接口重命名文件夹")
        dst_p = cls.resolve(dst)
        if dst_p.suffix.lower() not in DOC_SUFFIXES:
            dst_p = dst_p.with_suffix(".html")
        if dst_p.exists():
            raise WorkspaceError("目标路径已存在")
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        src_p.rename(dst_p)
        return cls.read_doc(dst_p.relative_to(cls.root()).as_posix())

    @classmethod
    def mkdir(cls, rel_path: str) -> None:
        target = cls.resolve(rel_path)
        target.mkdir(parents=True, exist_ok=True)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _title_of(path: Path) -> str:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:8192]
        except OSError:
            return path.stem
        return Workspace._title_from_html(head) or path.stem

    @staticmethod
    def _title_from_html(html: str) -> Optional[str]:
        if not html:
            return None
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string and soup.title.string.strip():
                return soup.title.string.strip()
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                return h1.get_text(strip=True)
        except Exception:  # noqa: BLE001
            m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if m:
                return m.group(1).strip()
        return None


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
