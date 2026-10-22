"""Target kinds. A template path targets/<kind>/<address>.tpl says where values go:

    file/<path under root>              a dotenv file, e.g. file/shop/apps/web/.env.local
    vercel/<project>/<environment>      production | preview | development
    railway/<project>/<environment>/<service>
    supabase/<project ref>              Edge Function secrets
    fly/<app>      worker/<name>      github/<owner>/<repo>[/<environment>]      gcp/<project>

Each kind can write values, maybe read them back, and maybe redeploy.
Only the given variables are written; nothing else at the target changes.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from .util import RekeyError, api, private_file, run, succeeds

Values = dict[str, str]


@dataclass
class Kind:
    write: Callable[[Any, list[str], Values], tuple | None]          # returns a deploy action or None
    read: Callable[[Any, list[str], list[str]], dict[str, str | None]] | None = None   # None value = exists, unreadable
    login: tuple[list[str], list[str]] | None = None                 # (check command, login command)


# ================================================================ dotenv files

_LINE = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")


def _closed(raw: str, q: str) -> bool:
    i = 1
    while i < len(raw):
        if raw[i] == "\\" and q == '"':
            i += 2
            continue
        if raw[i] == q:
            return True
        i += 1
    return False


def _assignments(lines: list[str]) -> list[tuple[int, int, re.Match | None]]:
    """(first line, last line, match) per logical assignment; quoted values may span lines."""
    out, i = [], 0
    while i < len(lines):
        m = _LINE.match(lines[i].rstrip("\n"))
        j = i
        if m and m.group(4)[:1] in "'\"" and m.group(4) and not _closed(m.group(4), m.group(4)[0]):
            q = m.group(4)[0]
            while j + 1 < len(lines) and not _closed(q + lines[j + 1].rstrip("\n"), q):
                j += 1
            j = min(j + 1, len(lines) - 1)
        out.append((i, j, m))
        i = j + 1
    return out


def _unquote(raw: str) -> str:
    raw = raw.strip()
    if len(raw) > 1 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if len(raw) > 1 and raw[0] == raw[-1] == '"':
        return re.sub(r"\\(.)", lambda m: {"n": "\n"}.get(m.group(1), m.group(1)), raw[1:-1])
    return re.sub(r"\s+#.*$", "", raw)


def _quote(value: str, old_raw: str) -> str:
    q = old_raw[:1] if old_raw[:1] in "'\"" else ""
    plain = re.fullmatch(r"[A-Za-z0-9_\-.:/@+=,%~]*", value) is not None and value != ""
    if q == "'" and "'" not in value or not q and not plain and "'" not in value:
        return f"'{value}'"
    if q == '"' or not plain:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return value


def parse_dotenv(text: str) -> dict[str, str]:
    lines = text.splitlines(keepends=True)
    out = {}
    for i, j, m in _assignments(lines):
        if m:
            raw = m.group(4) + ("\n" + "".join(lines[i + 1 : j + 1]).rstrip("\n") if j > i else "")
            out[m.group(2)] = _unquote(raw)
    return out


def _path(ctx, address: list[str]) -> str:
    return os.path.join(ctx.root, *address)


def write_file(ctx, address: list[str], values: Values) -> None:
    path = _path(ctx, address)
    lines: list[str] = []
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()
    todo, out = dict(values), []
    for i, j, m in _assignments(lines):
        if m and m.group(2) in todo:
            out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{_quote(todo.pop(m.group(2)), m.group(4))}\n")
        else:
            out.extend(lines[i : j + 1])
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    out += [f"{k}={_quote(v, '')}\n" for k, v in todo.items()]
    if ctx.dry_run:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o600
    fd = os.open(path + ".rekey", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as f:
        f.writelines(out)
    os.replace(path + ".rekey", path)
    return None


def read_file(ctx, address: list[str], names: list[str]) -> dict[str, str | None]:
    path = _path(ctx, address)
    if not os.path.exists(path):
        return {}
    with open(path, errors="ignore") as f:
        return parse_dotenv(f.read())


# ================================================================ Vercel (REST API, token from `vercel login`)


def vercel_token() -> str:
    if os.environ.get("VERCEL_TOKEN"):
        return os.environ["VERCEL_TOKEN"]
    for p in ("~/Library/Application Support/com.vercel.cli/auth.json", "~/.local/share/com.vercel.cli/auth.json"):
        p = os.path.expanduser(p)
        if os.path.exists(p):
            with open(p) as f:
                if tok := json.load(f).get("token"):
                    return tok
    raise RekeyError("vercel login 필요")


def _vercel(ctx, method: str, path: str, body: Any = None, team: str | None = None) -> Any:
    q = f"{'&' if '?' in path else '?'}teamId={team}" if team else ""
    return api(method, f"https://api.vercel.com{path}{q}", ctx.cached("vercel-token", vercel_token), body)


def vercel_project(ctx, name: str) -> tuple[str, str | None]:
    """(project id, team id): looks in every team the token can see."""
    def find() -> tuple[str, str | None]:
        teams = [t["id"] for t in _vercel(ctx, "GET", "/v2/teams").get("teams", [])] + [None]
        for team in teams:
            try:
                return _vercel(ctx, "GET", f"/v9/projects/{name}", team=team)["id"], team
            except RekeyError:
                continue
        raise RekeyError(f"Vercel 프로젝트 '{name}'를 찾지 못했습니다")
    return ctx.cached(f"vercel:{name}", find)


def vercel_envs(ctx, project: str) -> list[dict]:
    pid, team = vercel_project(ctx, project)
    return _vercel(ctx, "GET", f"/v9/projects/{pid}/env", team=team).get("envs", [])


def write_vercel(ctx, address: list[str], values: Values) -> tuple | None:
    project, env = address
    if ctx.dry_run:
        return ("vercel", project) if env == "production" else None
    pid, team = vercel_project(ctx, project)
    existing = [e for e in vercel_envs(ctx, project) if env in (e.get("target") or []) and not e.get("gitBranch")]
    for var, value in values.items():
        hits = [e for e in existing if e["key"] == var]
        for e in hits:
            _vercel(ctx, "PATCH", f"/v9/projects/{pid}/env/{e['id']}", {"value": value}, team)
        if not hits:   # new keys can't be read back from the dashboard; plain settings stay readable
            kind_ = "sensitive" if var in getattr(ctx, "secret_vars", ()) and env != "development" else "encrypted"
            _vercel(ctx, "POST", f"/v10/projects/{pid}/env", {"key": var, "value": value, "type": kind_, "target": [env]}, team)
    return ("vercel", project) if env == "production" else None


def read_vercel(ctx, address: list[str], names: list[str]) -> dict[str, str | None]:
    """The list endpoint returns ciphertext even with decrypt=true; one request per variable decrypts."""
    project, env = address
    pid, team = vercel_project(ctx, project)
    out: dict[str, str | None] = {}
    for e in vercel_envs(ctx, project):
        if env in (e.get("target") or []) and not e.get("gitBranch") and (not names or e["key"] in names):
            out[e["key"]] = None if e.get("type") == "sensitive" else \
                _vercel(ctx, "GET", f"/v1/projects/{pid}/env/{e['id']}", team=team).get("value")
    return out


def deploy_vercel(ctx, project: str) -> Callable[[], str]:
    pid, team = vercel_project(ctx, project)
    deps = _vercel(ctx, "GET", f"/v6/deployments?projectId={pid}&target=production&state=READY&limit=1", team=team)["deployments"]
    if not deps:
        return lambda: "NONE"
    d = _vercel(ctx, "POST", "/v13/deployments?forceNew=1", {"name": project, "deploymentId": deps[0]["uid"], "target": "production"}, team)
    return lambda: _vercel(ctx, "GET", f"/v13/deployments/{d['id']}", team=team).get("readyState", "?")


# ================================================================ Railway (CLI)


def railway_bin() -> str:
    local = os.path.expanduser("~/.railway/bin/railway")
    return local if os.path.exists(local) else "railway"


def _railway_id(ctx, project: str) -> str:
    def find() -> str:
        for p in json.loads(run([railway_bin(), "list", "--json"], timeout=60).stdout):
            if p.get("name") == project or p.get("id") == project:
                return p["id"]
        raise RekeyError(f"Railway 프로젝트 '{project}'를 찾지 못했습니다")
    return ctx.cached(f"railway:{project}", find)


def _railway_args(ctx, address: list[str]) -> list[str]:
    project, env, service = address
    return ["-p", _railway_id(ctx, project), "-e", env, "-s", service]


def write_railway(ctx, address: list[str], values: Values) -> tuple | None:
    if not ctx.dry_run:
        for var, value in values.items():
            run([railway_bin(), "variable", "set", var, "--stdin", "--skip-deploys", *_railway_args(ctx, address)], stdin=value, timeout=60)
    return ("railway", *address)


def read_railway(ctx, address: list[str], names: list[str]) -> dict[str, str | None]:
    return json.loads(run([railway_bin(), "variable", "list", "--json", *_railway_args(ctx, address)], timeout=60).stdout)


def deploy_railway(ctx, *address: str) -> Callable[[], str]:
    args = _railway_args(ctx, list(address))
    run([railway_bin(), "redeploy", "-y", *args], timeout=120)

    def status() -> str:
        rows = json.loads(run([railway_bin(), "deployment", "list", "--json", "--limit", "1", *args], timeout=60).stdout)
        rows = rows if isinstance(rows, list) else rows.get("deployments", [])
        return (rows[0].get("status") or "?").upper() if rows else "?"
    return status


# ================================================================ the rest (write only)


def write_supabase(ctx, address: list[str], values: Values) -> None:
    if not ctx.dry_run:
        with private_file("".join(f"{k}={json.dumps(v)}\n" for k, v in values.items()), ".env") as path:
            run(["supabase", "secrets", "set", "--project-ref", address[0], "--env-file", path], timeout=120)


def write_fly(ctx, address: list[str], values: Values) -> None:
    if not ctx.dry_run:
        body = "".join(f'{k}="""{v}"""\n' if "\n" in v or '"' in v else f"{k}={v}\n" for k, v in values.items())
        run(["fly", "secrets", "import", "-a", address[0]], stdin=body)


def write_worker(ctx, address: list[str], values: Values) -> None:
    if not ctx.dry_run:
        with private_file(json.dumps(values), ".json") as path:
            run(["npx", "--yes", "wrangler", "secret", "bulk", path, "--name", address[0]], timeout=180)


def write_github(ctx, address: list[str], values: Values) -> None:
    if not ctx.dry_run:
        env = ["-e", address[2]] if len(address) > 2 else []
        for var, value in values.items():
            run(["gh", "secret", "set", var, "-R", "/".join(address[:2]), *env], stdin=value, timeout=60)


def write_gcp(ctx, address: list[str], values: Values) -> None:
    if not ctx.dry_run:
        for var, value in values.items():
            run(["gcloud", "secrets", "versions", "add", var, "--project", address[0], "--data-file=-"], stdin=value, timeout=60)


def read_gcp(ctx, address: list[str], names: list[str]) -> dict[str, str | None]:
    out = {}
    for var in names:
        p = run(["gcloud", "secrets", "versions", "access", "latest", "--secret", var, "--project", address[0]], check=False, timeout=60)
        if p.returncode == 0:
            out[var] = p.stdout
    return out


KINDS: dict[str, Kind] = {
    "file": Kind(write_file, read_file),
    "vercel": Kind(write_vercel, read_vercel, (["vercel", "whoami"], ["vercel", "login"])),
    "railway": Kind(write_railway, read_railway, ([railway_bin(), "whoami"], [railway_bin(), "login"])),
    "supabase": Kind(write_supabase, None, (["supabase", "projects", "list"], ["supabase", "login"])),
    "fly": Kind(write_fly, None, (["fly", "auth", "whoami"], ["fly", "auth", "login"])),
    "worker": Kind(write_worker, None, (["npx", "--yes", "wrangler", "whoami"], ["npx", "--yes", "wrangler", "login"])),
    "github": Kind(write_github, None, (["gh", "auth", "status"], ["gh", "auth", "login", "-w"])),
    "gcp": Kind(write_gcp, read_gcp, (["gcloud", "auth", "print-access-token"], ["gcloud", "auth", "login"])),
}
DEPLOY = {"vercel": deploy_vercel, "railway": deploy_railway}
HEALTHY, BROKEN = {"READY", "SUCCESS"}, {"ERROR", "CANCELED", "FAILED", "CRASHED", "REMOVED"}


def kind(name: str) -> Kind:
    if name not in KINDS:
        raise RekeyError(f"모르는 대상 종류: {name} (가능: {', '.join(KINDS)})")
    return KINDS[name]


def logged_in(name: str) -> bool:
    k = KINDS.get(name)
    return not k or not k.login or succeeds(k.login[0])
