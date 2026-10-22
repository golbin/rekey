"""Small helpers. Rule for the whole codebase: secret values go to child processes on
stdin or through 0600 temp files. They are never printed or logged."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, Iterator

from .i18n import _


class RekeyError(Exception):
    """An error whose message is meant for the person running rekey."""


# ---------------------------------------------------------------- output

_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def say(msg: str = "") -> None:
    print(msg, flush=True)


def ok(msg: str) -> None:
    say(_c("32", "  ✓ ") + msg)


def warn(msg: str) -> None:
    say(_c("33", "  ! ") + msg)


def fail(msg: str) -> None:
    say(_c("31", "  ✗ ") + msg)


def step(msg: str) -> None:
    say(_c("36;1", "▸ ") + _c("1", msg))


def dim(text: str) -> str:
    return _c("2", text)


def bold(text: str) -> str:
    return _c("1", text)


# ---------------------------------------------------------------- values


def new_secret(fmt: str = "hex") -> str:
    if fmt == "password":  # letters and digits only: survives URLs and shells unescaped
        abc = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
        return "".join(secrets.choice(abc) for _ in range(32))
    return secrets.token_hex(32)


# ---------------------------------------------------------------- processes


def pmap(fn: Callable, xs: Iterable) -> list:
    """map() over network calls, eight at a time."""
    with ThreadPoolExecutor(8) as pool:
        return list(pool.map(fn, xs))


def run(cmd: list[str], *, stdin: str | None = None, cwd: str | None = None,
        check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(cmd, input=stdin, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise RekeyError(_("`{cmd}` is not installed", cmd=cmd[0]))
    except subprocess.TimeoutExpired:
        raise RekeyError(_("`{cmd}` timed out", cmd=" ".join(cmd[:3])))
    if check and p.returncode:
        # These CLIs never echo stdin, so their stderr is safe to show.
        tail = (p.stderr or p.stdout).strip().splitlines()[-4:]
        raise RekeyError(_("`{cmd}` failed:", cmd=" ".join(cmd[:4])) + " " + " / ".join(tail))
    return p


def succeeds(cmd: list[str]) -> bool:
    try:
        return run(cmd, check=False, timeout=40).returncode == 0
    except RekeyError:
        return False


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@contextlib.contextmanager
def private_file(content: str, suffix: str = "") -> Iterator[str]:
    """A 0600 temp file, removed afterwards, for CLIs that only read files."""
    fd, path = tempfile.mkstemp(prefix="rekey-", suffix=suffix)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        yield path
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)


# ---------------------------------------------------------------- HTTP


def http(method: str, url: str, *, headers: dict[str, str] | None = None, body: Any = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": "rekey", **({"Content-Type": "application/json"} if data else {}), **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, raw = r.status, r.read()
            break
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
            break
        except (urllib.error.URLError, OSError) as e:      # OSError: a read that timed out
            # Reads are safe to try again; a POST may already have made a key, so it isn't repeated.
            if attempt == 2 or method != "GET":
                raise RekeyError(f"{method} {urllib.parse.urlsplit(url).netloc}: {getattr(e, 'reason', e)}")
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw.decode(errors="replace")


def api(method: str, url: str, token: str, body: Any = None, scheme: str = "Bearer") -> Any:
    status, data = http(method, url, headers={"Authorization": f"{scheme} {token}"}, body=body)
    if status >= 300:
        raise RekeyError(f"{method} {urllib.parse.urlsplit(url).path} → {status}: {str(data)[:200]}")
    return data


# ---------------------------------------------------------------- the person


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask(question: str, default: bool = True) -> bool:
    if not interactive():
        return False
    ans = input(question + (" [Y/n] " if default else " [y/N] ")).strip().lower()
    return default if not ans else ans in ("y", "yes", "ㅇ", "네", "응", "是", "好", "はい", "s", "si", "sí")


def open_url(url: str) -> None:
    if url and not os.environ.get("REKEY_NO_BROWSER"):
        run(["open" if sys.platform == "darwin" else "xdg-open", url], check=False)


def clipboard() -> str:
    if sys.platform == "darwin":
        return run(["pbpaste"]).stdout.strip()
    return run(["wl-paste", "-n"] if have("wl-paste") else ["xclip", "-o", "-selection", "clipboard"]).stdout.strip()


def set_clipboard(value: str) -> None:
    if sys.platform == "darwin":
        run(["pbcopy"], stdin=value)
    else:
        run(["wl-copy"] if have("wl-copy") else ["xclip", "-selection", "clipboard"], stdin=value)
