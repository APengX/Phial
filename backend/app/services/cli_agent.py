"""Run a local CLI coding agent (Claude Code / Codex / Gemini) as a subprocess
in the workspace folder, feed it a prompt, and stream its stdout back.

Phial treats the CLI as a black box that returns text: the prompt asks it to
emit a complete HTML document, and we extract the HTML from whatever it prints
(see html_agent.extract_html). Configured env vars are merged into the child's
environment so users can point a CLI at a custom gateway / key / model.
"""

import os
import queue
import shutil
import subprocess
import threading
import time
from typing import Dict, Iterator, Optional

from ..utils.logger import get_logger
from . import agents as agents_svc
from .workspace import Workspace

logger = get_logger("phial.cli_agent")

_MAX_SECONDS = 240
_STDOUT_CHUNK = 256


class CliAgentError(Exception):
    """Raised when the CLI is missing, exits non-zero, or times out."""


def ensure_available(provider: str) -> dict:
    a = agents_svc.find(provider)
    if not a:
        raise CliAgentError(f"未知 agent: {provider}")
    if shutil.which(a["bin"]) is None:
        raise CliAgentError(
            f"未检测到 {a['name']} 的命令 `{a['bin']}`。请先安装并确保它在 PATH 中：{a['doc_url']}"
        )
    return a


def _merged_env(env_extra: Optional[Dict[str, str]]) -> Dict[str, str]:
    env = dict(os.environ)
    # Defense in depth: even if a stale settings file holds extra keys, only the
    # allow-listed ones reach the child (see agents_svc.ALLOWED_ENV_KEYS).
    for k, v in agents_svc.filter_env(env_extra).items():
        env[k] = v
    return env


def stream(
    provider: str,
    prompt: str,
    model: str = "",
    env_extra: Optional[Dict[str, str]] = None,
) -> Iterator[str]:
    a = ensure_available(provider)
    path = shutil.which(a["bin"])
    eff_model = model or a["default_model"]
    argv, stdin_text = a["build"](eff_model, prompt)
    argv = [path] + argv[1:]  # exec the resolved absolute path
    cwd = str(Workspace.root())
    logger.info("agent run: %s%s (cwd=%s)", a["bin"], f" --model {eff_model}" if eff_model else "", cwd)

    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=_merged_env(env_extra),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise CliAgentError(f"无法执行 {a['bin']}：{exc}")

    # feed stdin in a thread (large prompts can exceed the pipe buffer)
    def feed():
        try:
            if stdin_text is not None:
                proc.stdin.write(stdin_text)
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=feed, daemon=True).start()

    # drain stderr in a thread so the child never blocks on a full stderr pipe
    err_chunks = []

    def drain_err():
        try:
            for line in proc.stderr:
                err_chunks.append(line)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=drain_err, daemon=True).start()

    # stdout -> queue
    q: "queue.Queue" = queue.Queue()

    def read_out():
        try:
            while True:
                chunk = proc.stdout.read(_STDOUT_CHUNK)
                if not chunk:
                    break
                q.put(("out", chunk))
        finally:
            q.put(("end", None))

    threading.Thread(target=read_out, daemon=True).start()

    deadline = time.time() + _MAX_SECONDS
    produced = False
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                proc.kill()
                raise CliAgentError(f"{a['name']} 超时（> {_MAX_SECONDS}s）")
            try:
                kind, val = q.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                continue
            if kind == "end":
                break
            produced = True
            yield val
    except GeneratorExit:
        # Client went away mid-stream — don't leave the CLI process running.
        logger.info("agent stream closed by client; killing %s", a["bin"])
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        raise

    rc = proc.wait()
    # give the stderr drainer a beat to finish
    err = "".join(err_chunks).strip()
    if rc != 0:
        tail = err[-1000:] if err else "(无 stderr 输出)"
        raise CliAgentError(f"{a['name']} 退出码 {rc}：{tail}")
    if not produced and err:
        # some CLIs write the answer to stderr
        yield err


def run(
    provider: str,
    prompt: str,
    model: str = "",
    env_extra: Optional[Dict[str, str]] = None,
) -> str:
    return "".join(stream(provider, prompt, model=model, env_extra=env_extra))
