"""Per-document context folders — local directories whose files Phial
splices into the AI prompt for a given .html document.

Binding model: each document under the active workspace owns a list of
absolute folder paths. The bindings live in ~/.phial/settings.json under
`docContext`, keyed by workspace root then doc relpath, so they survive
restarts but stay decoupled from the docs themselves.

When the AI panel sends a message, `bundle_for(doc_relpath)` walks each
attached folder, reads every text file under it (whitelisted extensions,
skipping the obvious noise — .git, node_modules, build output), and
concatenates a single text blob that the API layer drops into the prompt
before the user's request. The blob is capped at `MAX_TOTAL_CHARS`;
anything past the cap is replaced by a "(remaining files truncated)"
listing so the model still knows what wasn't shown.
"""

from pathlib import Path
from typing import Iterable, List

from ..utils.logger import get_logger
from . import app_settings
from .workspace import Workspace

logger = get_logger("phial.context_folder")

_SETTINGS_KEY = "docContext"

# Defaults sized for a typical mid-context model. The block lands in the
# prompt alongside the document, history, etc.; 80k chars ≈ 20-25k tokens.
MAX_TOTAL_CHARS = 80_000
MAX_FILE_BYTES = 256 * 1024       # skip individual files bigger than this
MAX_FILES_LISTED = 2000           # hard ceiling on how many files we'll consider

# Whitelist by extension. Anything not on the list is silently skipped so a
# folder full of binaries / lockfiles / images doesn't blow the cap.
TEXT_EXTENSIONS = {
    ".py", ".pyi", ".pyw",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".vue", ".svelte", ".astro",
    ".html", ".htm",
    ".css", ".scss", ".sass", ".less",
    ".md", ".markdown", ".mdx", ".rst", ".org", ".txt",
    ".json", ".jsonc", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
    ".go", ".rs", ".java", ".kt", ".kts", ".scala",
    ".rb", ".php", ".pl",
    ".sh", ".bash", ".zsh", ".fish",
    ".sql",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx",
    ".swift", ".m", ".mm",
    ".lua", ".r", ".clj", ".ex", ".exs", ".erl", ".elm", ".dart",
    ".gradle", ".xml", ".tex",
}

# Files without an extension that are almost always worth showing.
NO_EXT_NAMES = {
    "README", "LICENSE", "LICENCE", "CHANGELOG", "NOTICE", "AUTHORS",
    "Dockerfile", "Makefile", "Procfile",
}

# Directories we never descend into. Typical build / cache / VCS noise.
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env",
    "dist", "build", "out", "target",
    ".next", ".nuxt", ".turbo", ".vite", ".cache",
    "coverage", ".tox",
    ".idea", ".vscode", ".vs",
}


class ContextFolderError(Exception):
    """Raised for invalid paths / IO problems the API should turn into 4xx."""


# ---------------------------------------------------------------------------
# Persistence (shape under ~/.phial/settings.json):
#   {
#     "docContext": {
#       "<workspace_abs_path>": {
#         "<doc_relpath>": ["<folder_abs_path>", ...]
#       }
#     }
#   }
# ---------------------------------------------------------------------------

def _root_key() -> str:
    return str(Workspace.root())


def _all() -> dict:
    data = app_settings.get(_SETTINGS_KEY)
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    app_settings.set_key(_SETTINGS_KEY, data)


def _normalize_doc(doc_rel: str) -> str:
    rel = (doc_rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel:
        raise ContextFolderError("缺少文档路径")
    return rel


def _bindings(doc_rel: str) -> List[str]:
    raw = _all().get(_root_key(), {}).get(doc_rel, [])
    return [str(p) for p in raw if isinstance(p, str)]


def _write_bindings(doc_rel: str, folders: List[str]) -> None:
    """Replace the binding list for one doc; prune empty branches so the
    settings file stays compact when everything is cleared."""
    data = _all()
    rk = _root_key()
    by_doc = dict(data.get(rk) or {})
    if folders:
        by_doc[doc_rel] = folders
    else:
        by_doc.pop(doc_rel, None)
    if by_doc:
        data[rk] = by_doc
    else:
        data.pop(rk, None)
    _save(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_for(doc_rel: str) -> List[dict]:
    rel = _normalize_doc(doc_rel)
    return [_summarize(p) for p in _bindings(rel)]


def all_for_workspace() -> dict:
    """Map of {doc_relpath: [folder summaries...]} for the active workspace.
    Lets the home page show counts for every doc in one round trip."""
    by_doc = _all().get(_root_key()) or {}
    return {rel: [_summarize(p) for p in folders] for rel, folders in by_doc.items()}


def add_for(doc_rel: str, folder: str) -> List[dict]:
    rel = _normalize_doc(doc_rel)
    if not folder or not folder.strip():
        raise ContextFolderError("缺少文件夹路径")
    fp = Path(folder.strip()).expanduser()
    if not fp.exists():
        raise ContextFolderError(f"文件夹不存在: {fp}")
    if not fp.is_dir():
        raise ContextFolderError(f"不是一个文件夹: {fp}")
    try:
        abs_path = str(fp.resolve())
    except OSError as exc:
        raise ContextFolderError(f"无法解析路径: {exc}") from exc
    folders = _bindings(rel)
    if abs_path in folders:
        return list_for(rel)
    folders.append(abs_path)
    _write_bindings(rel, folders)
    logger.info("context folder + %s for %s", abs_path, rel)
    return list_for(rel)


def remove_for(doc_rel: str, folder: str) -> List[dict]:
    rel = _normalize_doc(doc_rel)
    if not folder or not folder.strip():
        raise ContextFolderError("缺少文件夹路径")
    # Compare in two ways: as-stored (may be unresolved) and resolved. This
    # makes deletes work even after the folder was moved/renamed on disk.
    target_raw = folder.strip()
    try:
        target_resolved = str(Path(target_raw).expanduser().resolve())
    except OSError:
        target_resolved = target_raw
    folders = [f for f in _bindings(rel) if f != target_raw and f != target_resolved]
    _write_bindings(rel, folders)
    return list_for(rel)


def bundle_for(doc_rel: str, *, max_chars: int = MAX_TOTAL_CHARS) -> str:
    """Concatenate the bound folders' text files into one prompt-ready blob.

    Returns "" when there are no bindings (or all of them are unreadable),
    so callers can drop the block entirely without a guard.
    """
    try:
        rel = _normalize_doc(doc_rel)
    except ContextFolderError:
        return ""
    folders = _bindings(rel)
    if not folders:
        return ""

    pieces: List[str] = []
    remaining = max_chars
    overflow: List[str] = []  # display names of files that didn't fit

    for folder in folders:
        root = Path(folder)
        if not root.exists() or not root.is_dir():
            note = f"## [missing] {folder}\n（文件夹不存在或已被移动）\n"
            pieces.append(note)
            remaining -= len(note)
            continue

        files = sorted(_iter_text_files(root))
        header = f"## 文件夹: {root}（共 {len(files)} 个文本文件）\n"
        pieces.append(header)
        remaining -= len(header)

        if not files:
            pieces.append("（没有可读的文本文件）\n")
            continue

        for fp in files:
            try:
                rel_name = fp.relative_to(root).as_posix()
            except ValueError:
                rel_name = fp.name
            label = f"\n### {rel_name}\n"

            if remaining <= len(label) + 64:
                overflow.append(rel_name)
                continue

            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            block = label + "```\n" + content + "\n```\n"
            if len(block) <= remaining:
                pieces.append(block)
                remaining -= len(block)
                continue

            # Doesn't fit whole — keep a useful prefix if there's room, else
            # punt it to the overflow list.
            head_room = remaining - len(label) - len("```\n\n... (truncated)\n```\n")
            if head_room >= 400:
                truncated = label + "```\n" + content[:head_room] + "\n... (truncated)\n```\n"
                pieces.append(truncated)
                remaining = 0
            else:
                overflow.append(rel_name)

    if overflow:
        tail = (
            "\n## 未塞进 prompt 的其他文件（受总字符上限限制）\n"
            + "\n".join(f"- {n}" for n in overflow[:200])
            + "\n"
        )
        pieces.append(tail)

    return "".join(pieces).strip()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _summarize(abs_path: str) -> dict:
    p = Path(abs_path)
    out: dict = {"path": abs_path, "name": p.name or abs_path}
    if not p.exists() or not p.is_dir():
        out.update(missing=True, fileCount=0, totalBytes=0)
        return out
    files = list(_iter_text_files(p))
    out["fileCount"] = len(files)
    out["totalBytes"] = sum(_safe_size(f) for f in files)
    return out


def _safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def _iter_text_files(root: Path) -> Iterable[Path]:
    """Yield text-looking files under `root` (after the SKIP_DIRS prune)."""
    count = 0
    for path in _walk(root):
        if count >= MAX_FILES_LISTED:
            return
        if not _looks_textual(path):
            continue
        if _safe_size(path) > MAX_FILE_BYTES:
            continue
        count += 1
        yield path


def _looks_textual(p: Path) -> bool:
    suffix = p.suffix.lower()
    if suffix:
        return suffix in TEXT_EXTENSIONS
    return p.name in NO_EXT_NAMES


def _walk(root: Path) -> Iterable[Path]:
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    entries.sort(key=lambda p: (p.is_file(), p.name.lower()))
    for entry in entries:
        # Skip dotfiles/dotdirs (covers .git, .env, .DS_Store, …) and the
        # named noise dirs (node_modules, dist, …).
        if entry.name.startswith(".") or entry.name in SKIP_DIRS:
            continue
        if entry.is_dir():
            yield from _walk(entry)
        elif entry.is_file():
            yield entry
