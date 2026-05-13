"""Per-document context — what gets spliced into the AI prompt for a given doc.

Two kinds of pickables, both opt-in (default = nothing sent):

* **Bound folders.** A doc can bind one or more local folders ("here are the
  code / notes I might want to reference"). From each bound folder the user
  then **picks individual files** to include in the next message. Binding a
  folder alone sends *nothing* — picking is the act that puts a file in front
  of the model.

* **Workspace docs.** Any other `.html` doc in the active workspace can be
  picked so the model can read its content (handy for cross-doc linking
  and "rewrite this one to match the structure of that one").

Persisted shape under `~/.phial/settings.json -> docContext`:

    {
      "<workspace_abs>": {
        "<doc-rel>.html": {
          "folders": [
            {"path": "<folder-abs>", "picks": ["src/foo.py", "README.md"]}
          ],
          "docs": ["other.html", "notes/sub.html"]
        }
      }
    }

The older shape (a flat list of folder paths, no picks) is read transparently
and normalized to the new shape; the next write upgrades it on disk.
"""

from pathlib import Path
from typing import Iterable, List, Optional

from ..utils.logger import get_logger
from . import app_settings
from .workspace import DOC_SUFFIXES, Workspace

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
# Persistence — load / normalize / save
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


def _normalize_entry(raw) -> dict:
    """Coerce one doc's stored value into `{folders:[{path,picks}], docs:[]}`.

    Accepts:
      - list[str]              (legacy: just folder paths, no picks)
      - dict with `folders`/`docs` (current shape)
      - dict with `folders` as list[str] (mid-migration)
    """
    if isinstance(raw, list):
        return {
            "folders": [{"path": str(p), "picks": []} for p in raw if isinstance(p, str)],
            "docs": [],
        }
    if not isinstance(raw, dict):
        return {"folders": [], "docs": []}

    folders_raw = raw.get("folders") or []
    folders: List[dict] = []
    for item in folders_raw:
        if isinstance(item, str):
            folders.append({"path": item, "picks": []})
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            picks = item.get("picks") or []
            folders.append({
                "path": item["path"],
                "picks": [str(x) for x in picks if isinstance(x, str)],
            })

    docs_raw = raw.get("docs") or []
    docs = [str(x) for x in docs_raw if isinstance(x, str)]

    return {"folders": folders, "docs": docs}


def _entry(doc_rel: str) -> dict:
    return _normalize_entry(_all().get(_root_key(), {}).get(doc_rel))


def _write_entry(doc_rel: str, entry: dict) -> None:
    """Replace this doc's entry; prune empty branches so the file stays small."""
    data = _all()
    rk = _root_key()
    by_doc = dict(data.get(rk) or {})
    is_empty = not entry.get("folders") and not entry.get("docs")
    if is_empty:
        by_doc.pop(doc_rel, None)
    else:
        by_doc[doc_rel] = entry
    if by_doc:
        data[rk] = by_doc
    else:
        data.pop(rk, None)
    _save(data)


# ---------------------------------------------------------------------------
# Public API — folder bindings (HomeView still calls these)
# ---------------------------------------------------------------------------

def list_for(doc_rel: str) -> List[dict]:
    rel = _normalize_doc(doc_rel)
    return [_summarize(f) for f in _entry(rel)["folders"]]


def all_for_workspace() -> dict:
    """Map of {doc_relpath: [folder summaries...]} for the active workspace.
    Lets the home page show counts for every doc in one round trip."""
    by_doc = _all().get(_root_key()) or {}
    out = {}
    for rel, raw in by_doc.items():
        entry = _normalize_entry(raw)
        if entry["folders"]:
            out[rel] = [_summarize(f) for f in entry["folders"]]
    return out


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

    entry = _entry(rel)
    if any(f["path"] == abs_path for f in entry["folders"]):
        return list_for(rel)
    entry["folders"].append({"path": abs_path, "picks": []})
    _write_entry(rel, entry)
    logger.info("context folder + %s for %s", abs_path, rel)
    return list_for(rel)


def remove_for(doc_rel: str, folder: str) -> List[dict]:
    rel = _normalize_doc(doc_rel)
    if not folder or not folder.strip():
        raise ContextFolderError("缺少文件夹路径")
    target_raw = folder.strip()
    try:
        target_resolved = str(Path(target_raw).expanduser().resolve())
    except OSError:
        target_resolved = target_raw

    entry = _entry(rel)
    entry["folders"] = [
        f for f in entry["folders"]
        if f["path"] != target_raw and f["path"] != target_resolved
    ]
    _write_entry(rel, entry)
    return list_for(rel)


# ---------------------------------------------------------------------------
# Public API — picks (the actual files / docs that get sent)
# ---------------------------------------------------------------------------

def get_picks(doc_rel: str) -> dict:
    """Return `{folders:[{path, picks}], docs:[...]}` for the picker UI.

    Stale picks (file no longer exists / folder missing) are kept so the user
    can see "this was selected but is gone" — the bundle step skips them.
    """
    rel = _normalize_doc(doc_rel)
    return _entry(rel)


def set_picks(doc_rel: str, *, folders: Optional[List[dict]] = None,
              docs: Optional[List[str]] = None) -> dict:
    """Replace the picks for one doc.

    `folders` is a list of `{path, picks}` — only bindings already attached to
    this doc are accepted; passing an unknown folder path is a 400 (rather than
    silently auto-binding). `docs` is workspace-relative `.html` paths;
    non-existent paths are dropped.
    """
    rel = _normalize_doc(doc_rel)
    entry = _entry(rel)
    known = {f["path"]: f for f in entry["folders"]}

    if folders is not None:
        if not isinstance(folders, list):
            raise ContextFolderError("folders 必须是数组")
        seen = set()
        for item in folders:
            if not isinstance(item, dict):
                raise ContextFolderError("folders 项格式错误")
            path = item.get("path")
            if not isinstance(path, str) or path not in known:
                raise ContextFolderError(f"folder 未绑定: {path}")
            picks_raw = item.get("picks") or []
            if not isinstance(picks_raw, list):
                raise ContextFolderError("picks 必须是数组")
            picks = []
            for p in picks_raw:
                if isinstance(p, str) and p:
                    norm = p.replace("\\", "/").lstrip("/")
                    if ".." in Path(norm).parts:
                        continue
                    picks.append(norm)
            known[path] = {"path": path, "picks": sorted(set(picks))}
            seen.add(path)
        # Folders not in the payload keep their existing picks (the picker UI
        # always sends all bound folders, but be defensive).
        entry["folders"] = [known[p] for p in [f["path"] for f in entry["folders"]]]

    if docs is not None:
        if not isinstance(docs, list):
            raise ContextFolderError("docs 必须是数组")
        clean = []
        for d in docs:
            if not isinstance(d, str) or not d.strip():
                continue
            norm = d.replace("\\", "/").strip().lstrip("/")
            if norm == rel:           # the doc itself is implicit context
                continue
            try:
                target = Workspace.resolve(norm, must_exist=True)
            except Exception:  # noqa: BLE001
                continue
            if target.suffix.lower() not in DOC_SUFFIXES:
                continue
            clean.append(target.relative_to(Workspace.root()).as_posix())
        entry["docs"] = sorted(set(clean))

    _write_entry(rel, entry)
    return get_picks(rel)


# ---------------------------------------------------------------------------
# Public API — discovery (what the picker UI shows)
# ---------------------------------------------------------------------------

def list_pickable(doc_rel: str, folder: str) -> List[dict]:
    """List the whitelisted files under one bound folder. Each item is
    `{rel, size}` with `rel` relative to the folder root (posix slashes)."""
    rel = _normalize_doc(doc_rel)
    if not folder:
        raise ContextFolderError("缺少文件夹路径")
    bound = {f["path"]: f for f in _entry(rel)["folders"]}
    if folder not in bound:
        raise ContextFolderError("folder 未绑定")

    root = Path(folder)
    if not root.exists() or not root.is_dir():
        raise ContextFolderError("文件夹不存在或已被移动")

    out: List[dict] = []
    for fp in _iter_text_files(root):
        try:
            rel_name = fp.relative_to(root).as_posix()
        except ValueError:
            continue
        out.append({"rel": rel_name, "size": _safe_size(fp)})
    out.sort(key=lambda d: d["rel"].lower())
    return out


def list_workspace_docs(exclude: Optional[str] = None) -> List[dict]:
    """All `.html` docs in the active workspace, for the cross-doc picker.
    `exclude` (workspace-rel) is dropped — usually the doc currently open."""
    root = Workspace.root()
    skip_self = _normalize_doc(exclude) if exclude else None
    out: List[dict] = []
    for fp in _walk_workspace(root):
        if fp.suffix.lower() not in DOC_SUFFIXES:
            continue
        rel = fp.relative_to(root).as_posix()
        if rel == skip_self:
            continue
        out.append({
            "rel": rel,
            "size": _safe_size(fp),
            "title": Workspace._title_of(fp),
        })
    out.sort(key=lambda d: d["rel"].lower())
    return out


# ---------------------------------------------------------------------------
# Bundling — what actually goes into the prompt
# ---------------------------------------------------------------------------

def bundle_for(doc_rel: str, *, max_chars: int = MAX_TOTAL_CHARS) -> str:
    """Concatenate the *picked* files (folder picks + cross-doc picks) into
    one prompt-ready blob. Returns "" when nothing is picked, so callers can
    drop the block entirely without a guard.
    """
    try:
        rel = _normalize_doc(doc_rel)
    except ContextFolderError:
        return ""

    entry = _entry(rel)
    has_anything = (
        any(f.get("picks") for f in entry["folders"]) or bool(entry["docs"])
    )
    if not has_anything:
        return ""

    pieces: List[str] = []
    remaining = max_chars
    overflow: List[str] = []

    # --- bound folders --------------------------------------------------
    for folder in entry["folders"]:
        picks = folder.get("picks") or []
        if not picks:
            continue
        root = Path(folder["path"])
        if not root.exists() or not root.is_dir():
            note = f"## [missing] {folder['path']}\n（文件夹不存在或已被移动）\n"
            pieces.append(note)
            remaining -= len(note)
            continue

        header = f"## 文件夹: {root}（已勾选 {len(picks)} 个文件）\n"
        pieces.append(header)
        remaining -= len(header)

        for rel_name in sorted(picks):
            fp = (root / rel_name).resolve()
            # Path-safety: ignore picks that resolve outside their folder.
            try:
                fp.relative_to(root.resolve())
            except ValueError:
                continue
            if not fp.exists() or not fp.is_file():
                pieces.append(f"\n### {rel_name}\n（已不存在）\n")
                continue
            remaining = _emit_file(pieces, fp, rel_name, remaining, overflow)

    # --- cross-doc picks (workspace .html) ------------------------------
    if entry["docs"]:
        ws_root = Workspace.root()
        header = f"## 工作区其它文档（已勾选 {len(entry['docs'])} 篇）\n"
        pieces.append(header)
        remaining -= len(header)
        for d_rel in sorted(entry["docs"]):
            try:
                target = Workspace.resolve(d_rel, must_exist=True)
            except Exception:  # noqa: BLE001
                pieces.append(f"\n### {d_rel}\n（已不存在）\n")
                continue
            label_rel = target.relative_to(ws_root).as_posix()
            remaining = _emit_file(pieces, target, label_rel, remaining, overflow)

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

def _summarize(folder: dict) -> dict:
    abs_path = folder["path"]
    picks = folder.get("picks") or []
    p = Path(abs_path)
    out: dict = {
        "path": abs_path,
        "name": p.name or abs_path,
        "pickedCount": len(picks),
    }
    if not p.exists() or not p.is_dir():
        out.update(missing=True, fileCount=0, totalBytes=0)
        return out
    files = list(_iter_text_files(p))
    out["fileCount"] = len(files)  # total available (for "X/Y" display)
    # totalBytes reflects only the *picked* files — that's what the AI gets.
    out["totalBytes"] = sum(_safe_size(p / r) for r in picks)
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


def _walk_workspace(root: Path) -> Iterable[Path]:
    """Like `_walk` but tuned for the workspace tree (skip dotfiles only —
    the workspace shouldn't have node_modules etc., and `.html` files
    elsewhere aren't text-file candidates anyway)."""
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            yield from _walk_workspace(entry)
        elif entry.is_file():
            yield entry


def _emit_file(pieces: List[str], fp: Path, rel_name: str,
               remaining: int, overflow: List[str]) -> int:
    """Append one file's labeled content to `pieces` and return updated
    `remaining`. Truncates with a marker if it doesn't fit whole; overflows
    are recorded by name for the summary footer."""
    label = f"\n### {rel_name}\n"
    if remaining <= len(label) + 64:
        overflow.append(rel_name)
        return remaining
    try:
        content = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return remaining

    block = label + "```\n" + content + "\n```\n"
    if len(block) <= remaining:
        pieces.append(block)
        return remaining - len(block)

    head_room = remaining - len(label) - len("```\n\n... (truncated)\n```\n")
    if head_room >= 400:
        truncated = label + "```\n" + content[:head_room] + "\n... (truncated)\n```\n"
        pieces.append(truncated)
        return 0
    overflow.append(rel_name)
    return remaining
