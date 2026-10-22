"""`rekey init`: write templates and keys.toml from what exists today.

One classifier is used for every source (.env files, Vercel, Railway, GCP Secret Manager):
a variable is either a key (→ a {{ op://... }} reference, grouped by value so a key copied
to ten places becomes one item) or a plain setting (→ written as is, except in local .env
files, where settings are personal and left alone). Existing templates are never touched.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from . import tpl
from .targets import _vercel, parse_dotenv, railway_bin, read_gcp, read_vercel
from .i18n import _
from .util import RekeyError, dim, fail, ok, run, say, step

SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".venv", "venv", "Pods", ".turbo", ".expo", "target", "third_party"}
PLATFORM = re.compile(r"^(VERCEL|VERCEL_.*|RAILWAY_.*|TURBO_.*|NX_.*)$")
PUBLIC = re.compile(r"^(EXPO_PUBLIC_|NEXT_PUBLIC_|VITE_|PUBLIC_)")    # shipped to browsers and apps: never a secret

# Variable name → provider. First match wins; "-" means "not a key".
NAMES = [
    ("-", r"^(EXPO_PUBLIC_|NEXT_PUBLIC_|VITE_|PUBLIC_)|_URL$|_EMAIL$|_IDS?$|_KEY_ID$|_PROJECT$|_REGION$|_BUCKET|^(ROOM|USER_AUTH)_TOKEN$"),
    ("anthropic", r"^ANTHROPIC_API_KEY$"), ("openai", r"^OPENAI_API_KEY$"), ("openrouter", r"^OPENROUTER_API_KEY$"),
    ("google-api-key", r"^(GEMINI|GOOGLE)_API_KEY$"),
    ("gcp-sa", r"(CREDENTIALS_JSON|SERVICE_ACCOUNT(_JSON)?(_BASE64)?|^GCP_SA_KEY)$"),
    ("google-oauth", r"CLIENT_SECRET$"), ("groq", r"^GROQ_"), ("upstage", r"^UPSTAGE_"), ("deepgram", r"^DEEPGRAM_"),
    ("assemblyai", r"^ASSEMBLYAI_"), ("elevenlabs", r"^ELEVENLABS_"), ("cartesia", r"^CARTESIA_"), ("daily", r"^DAILY_API"),
    ("heygen", r"^HEYGEN"), ("tavily", r"^TAVILY_"), ("brave", r"^BRAVE"),
    ("supabase", r"SUPABASE_(SERVICE_ROLE|SECRET)_KEY$"), ("supabase-token", r"^SUPABASE_ACCESS_TOKEN$"),
    ("cloudflare-turn", r"TURN_KEY_API_TOKEN$"), ("cloudflare", r"^CLOUDFLARE_.*TOKEN$"), ("resend", r"^RESEND_API_KEY$"),
    ("slack", r"SLACK_.*(TOKEN|SECRET)$|^SLACK_WEBHOOK"), ("polar", r"^POLAR_"),
    ("apple", r"^APNS_KEY$"), ("expo", r"^EXPO_ACCESS_TOKEN$"),
    ("fly", r"^FLY_API_"), ("vercel", r"^VERCEL_(ACCESS_)?TOKEN$"), ("github", r"^(GITHUB_PAT|GH_TOKEN)$"), ("sentry", r"^SENTRY_.*TOKEN$"),
    ("meta", r"^META_ACCESS_TOKEN$"), ("trigger", r"^TRIGGER_SECRET"), ("stripe", r"^STRIPE_(SECRET|RESTRICTED)_KEY$"),
    ("locked", r"MASTER_KEYS?$|ENCRYPTION_KEY$|_PAYLOAD_KEY$|_HASH_SECRET$|^SENSITIVE_KEY$"),
    ("self", r"^((BETTER_|NEXT)?AUTH|CRON|SESSION|JWT|COOKIE|REVALIDATE|ENCRYPTION)_SECRET$|^APP_SECRET$"),
    # Anything else that looks like a credential could belong to a third party: a person issues it in the browser.
    # Rename an item to <project>.self.<purpose> when it is a token only your own services share.
    ("other", r"SECRET|PASSWORD|_TOKEN$|_API_KEY$|_CLIENT_KEY$|_OTP(_CODE)?$"),
]
# The value's own prefix beats the name (QUALITY_LLM_API_KEY may hold an OpenAI key).
PREFIXES = [("sk-ant-", "anthropic"), ("sk-or-", "openrouter"), ("sk-", "openai"), ("AIza", "google-api-key"), ("re_", "resend"),
            ("gsk_", "groq"), ("sb_secret_", "supabase"), ("sntrys_", "sentry"), ("github_pat_", "github"), ("ghp_", "github"), ("sk_live_", "stripe"), ("rk_live_", "stripe"), ("rk_", "other")]
# Two variables that are one key: (provider, var, field, var, field).
PAIRS = [("cloudflare", "R2_ACCESS_KEY_ID", "access_key_id", "R2_SECRET_ACCESS_KEY", "secret_access_key"),
         ("cloudflare", "CLOUDFLARE_R2_ACCESS_KEY_ID", "access_key_id", "CLOUDFLARE_R2_SECRET_ACCESS_KEY", "secret_access_key"),
         ("other", "S3_ACCESS_KEY_ID", "access_key_id", "S3_SECRET_ACCESS_KEY", "secret_access_key"),
         ("ncp", "NCP_ACCESS_KEY", "access_key_id", "NCP_SECRET_KEY", "secret_access_key"),
         ("cloudflare-turn", "CLOUDFLARE_TURN_KEY_ID", "key_id", "CLOUDFLARE_TURN_KEY_API_TOKEN", "credential")]
NOTES = {
    "locked": "Encrypts or hashes data: changing it makes existing data unreadable. Add key versioning first.",
    "BETTER_AUTH_SECRET": "Changing it signs every user out.",
    "legacy": "Legacy JWT service_role key. The new secret keys are not JWTs: code that sends this as a Bearer JWT will break.",
}


def provider_of(var: str, value: str) -> str | None:
    name = next((p for p, rx in NAMES if re.search(rx, var)), None)
    if name in (None, "-"):
        return None
    if name in ("self", "other"):
        return next((p for pre, p in PREFIXES if value.startswith(pre)), name)
    return name


def looks_secret(var: str, value: str) -> bool:
    if provider_of(var, value) or any(value.startswith(p) for p, _prov in PREFIXES):
        return True
    if "-----BEGIN" in value or '"private_key"' in value or re.search(r"://[^/@\s]+:[^/@\s]+@", value):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9_\-+/=]{24,}", value) and re.search(r"\d", value) and re.search(r"[A-Z]", value))


# ================================================================ grouping values into items


class Index:
    """value → item. Items get a temporary name here; init() names them once every use is known."""

    def __init__(self, vault: str):
        self.vault = vault
        self.by_value: dict[str, str] = {}               # sha256(value) -> temporary name
        self.label: dict[str, str] = {}                  # temporary name -> preferred label (e.g. Supabase project)
        self.notes: dict[str, set[str]] = defaultdict(set)
        self.fixed: set[str] = set()                     # names already used by existing templates

    def seed(self, ctx) -> None:
        """Keep the names of keys that existing templates already use."""
        from .core import read_target
        from .store import FileStore

        items = set(ctx.items())
        if items and ctx.store.check():
            ctx.store = FileStore("")        # 1Password not reachable: read current values from the targets instead
        found: dict = defaultdict(dict)
        for vault in {v for v, _n in items}:
            say(dim("  " + _("Reading the keys in '{vault}'…", vault=vault)))
            for name, rec in ctx.store.read_all(vault).items():
                found[(vault, name)].update(rec.fields)
        # Keys missing from the store: read them back from where they are used, one read per target.
        for t in sorted(ctx.templates, key=lambda t: t.kind != "file"):
            if all(found.get(i) for i in t.items()):
                continue
            if t.kind != "file":
                say(dim(f"  · {t.rel}"))
            try:
                values = read_target(ctx, t, list(t.lines))
            except RekeyError:
                continue
            for var, raw in t.lines.items():
                for (v, n, f), value in (tpl.reverse(raw, values.get(var) or "") or {}).items():
                    found[(v, n)].setdefault(f, value)
        for item in items:
            f = found.get(item, {})
            pair = next(((fa, fb) for _p, _a, fa, _b, fb in PAIRS if fa in f and fb in f), None)
            if pair:
                value = f[pair[0]] + "\0" + f[pair[1]]
            elif f.get("credential_base64") and not f.get("credential"):
                value = base64.b64decode(f["credential_base64"]).decode(errors="replace")
            else:
                value = f.get("credential") or f.get("password")
            if value:
                self.by_value[hashlib.sha256(value.encode()).hexdigest()] = item[1]
                self.fixed.add(item[1])

    def item(self, prov: str, value: str) -> str:
        sha = hashlib.sha256(value.encode()).hexdigest()
        return self.by_value.setdefault(sha, f"{prov}.{sha[:12]}")

    def known(self, value: str) -> str | None:
        return self.by_value.get(hashlib.sha256(value.encode()).hexdigest())

    def ref(self, name: str, field: str = "credential") -> str:
        return tpl.ref(self.vault, name, field)


def classify(ix: Index, env: dict[str, str], *, settings: bool) -> dict[str, str]:
    """Template lines for one target's variables."""
    lines, used = {}, set()
    for prov, a, fa, b, fb in PAIRS:
        if env.get(a) and env.get(b):
            name = ix.item(prov, env[a].strip() + "\0" + env[b].strip())
            lines[a], lines[b] = ix.ref(name, fa), ix.ref(name, fb)
            used |= {a, b}
    for var, value in env.items():
        value = (value or "").strip()            # a stray trailing newline must not split one key into two
        if var in used or not value or PLATFORM.match(var):
            continue
        if PUBLIC.match(var):
            if settings:
                lines[var] = value.replace("\n", " ")
            continue
        u = urlsplit(value) if "://" in value else None
        if u and u.password and "supabase" in (u.hostname or ""):
            ref = (u.username or "").rpartition(".")[2] or (u.hostname or "").split(".")[1]
            name = ix.item("supabase-db", u.password)
            ix.label[name] = ref
            lines[var] = value.replace(f":{u.password}@", ":" + ix.ref(name, "password") + "@", 1)
            continue
        if var in ("DB_PASSWORD", "SUPABASE_DB_PASSWORD") and "." in env.get("DB_USER", ""):
            name = ix.item("supabase-db", value)
            ix.label[name] = env["DB_USER"].rpartition(".")[2]
            lines[var] = ix.ref(name, "password")
            continue
        prov = provider_of(var, value)
        if prov is None and looks_secret(var, value):
            prov = "other"
        if prov is None:
            if settings and not looks_secret(var, value):
                lines[var] = value.replace("\n", " ")
            continue
        field = "credential"
        if prov == "gcp-sa" and var.endswith("_BASE64"):
            field = "credential_base64"
        if prov == "gcp-sa" and field == "credential":
            try:
                json.loads(value)
            except ValueError:
                prov = "other"
        tag = prov
        if prov == "locked":
            prov, tag = "self", "locked"
        same = base64.b64decode(value).decode(errors="replace") if field == "credential_base64" else value
        name = ix.item(prov, same)
        if tag == "locked":
            ix.notes[name].add("locked")
        if var in NOTES:
            ix.notes[name].add(var)
        lines[var] = ix.ref(name, field)
    return lines


# ================================================================ sources


def env_files(root: str):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and d != "worktrees"]
        for fn in fns:
            if re.match(r"^(\.env.*|\.dev\.vars|.*\.env)$", fn) and not re.search(r"example|sample|xcode|\.tpl$|\.bak", fn):
                yield os.path.join(dp, fn)


def chosen_files(root: str, paths: list[str]):
    """Every .env file under root, or only the given files and folders."""
    if not paths:
        yield from env_files(root)
    for p in map(os.path.abspath, paths):
        if not p.startswith(os.path.abspath(root) + os.sep):
            raise RekeyError(_("{path} is outside {root} (set REKEY_ROOT)", path=p, root=root))
        if os.path.isdir(p):
            yield from env_files(p)
        elif os.path.isfile(p):
            yield p
        else:
            raise RekeyError(_("no such file: {path}", path=p))


def from_files(ix: Index, root: str, home: str, paths: list[str] = (), settings: bool = False) -> dict[str, dict[str, str]]:
    out = {}
    for path in chosen_files(root, list(paths)):
        rel = os.path.relpath(path, root)
        if rel.startswith(os.path.relpath(home, root)) or "/.vercel/" in rel:
            continue
        with open(path, errors="ignore") as f:
            lines = classify(ix, parse_dotenv(f.read()), settings=settings)
        if lines:
            out[f"file/{rel}"] = lines
    return out


def from_vercel(ix: Index, ctx, files: dict[str, dict[str, str]], root: str) -> dict[str, dict[str, str]]:
    """Readable values are classified; sensitive ones are matched by name to the linked folder's .env."""
    linked = defaultdict(list)
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and d != "worktrees"]
        if dp.endswith("/.vercel") and "project.json" in fns:
            with open(os.path.join(dp, "project.json")) as f:
                linked[json.load(f).get("projectName")].append(os.path.relpath(os.path.dirname(dp), root))
    out = {}
    teams = [t["id"] for t in _vercel(ctx, "GET", "/v2/teams").get("teams", [])]
    projects = [p["name"] for team in teams for p in _vercel(ctx, "GET", "/v9/projects?limit=100", team=team).get("projects", [])]
    for project in projects:
        for env in ("production", "preview", "development"):
            values = read_vercel(ctx, [project, env], [])
            readable = {k: v for k, v in values.items() if v is not None}
            lines = classify(ix, readable, settings=True)
            for var in (k for k, v in values.items() if v is None):
                guess = next((tl[var] for d in linked.get(project, []) for rel, tl in files.items()
                              if rel.startswith(f"file/{d}/") and var in tl), None)
                if guess:
                    lines["# " + var] = f"# {var}: guessed — Vercel hides this value; matched by name to the linked local .env"
                    lines[var] = guess
                else:
                    lines[var] = f"# {var}: sensitive in Vercel, value unknown (not managed)"
            if lines:
                out[f"vercel/{project}/{env}"] = lines
    return out


def from_supabase(ix: Index, ctx) -> dict[str, dict[str, str]]:
    """Edge Function secrets are listed as sha256 digests: matched against every known value."""
    from .providers import _supabase

    out = {}
    data = json.loads(run(["supabase", "projects", "list", "-o", "json"]).stdout)
    for p in data.get("projects", []) if isinstance(data, dict) else data:
        ref = p.get("ref") or p["id"]
        for k in _supabase(ctx, "GET", f"/v1/projects/{ref}/api-keys?reveal=true"):   # name supabase keys by project
            if (v := k.get("api_key")) and (hit := ix.known(v)) and hit.startswith("supabase."):
                ix.label[hit] = p["name"] + ("-legacy" if v.startswith("eyJ") else "")
                if v.startswith("eyJ"):
                    ix.notes[hit].add("legacy")
        rows = json.loads(run(["supabase", "secrets", "list", "--project-ref", ref, "-o", "json"], check=False).stdout or "[]")
        lines = {r["name"]: ix.ref(ix.by_value[r["value"]]) if r.get("value") in ix.by_value else f"# {r['name']}: value unknown (not managed)"
                 for r in rows if not r["name"].startswith("SUPABASE_")}
        if lines:
            out[f"supabase/{ref}"] = lines
    return out


def from_railway(ix: Index) -> dict[str, dict[str, str]]:
    out = {}
    def names(v) -> list[str]:
        rows = v.get("edges", []) if isinstance(v, dict) else v or []
        return [(r.get("node") or r)["name"] for r in rows]

    for p in json.loads(run([railway_bin(), "list", "--json"]).stdout):
        envs, services = names(p.get("environments")), names(p.get("services"))
        for env in envs:
            for svc in services:
                r = run([railway_bin(), "variable", "list", "--json", "-p", p["id"], "-e", env, "-s", svc], check=False)
                if r.returncode == 0 and (lines := classify(ix, json.loads(r.stdout), settings=True)):
                    out[f"railway/{p['name']}/{env}/{svc}"] = lines
    return out


def from_gcp(ix: Index, project: str) -> dict[str, dict[str, str]]:
    names = run(["gcloud", "secrets", "list", "--project", project, "--format", "value(name)"]).stdout.split()
    lines = classify(ix, read_gcp(None, [project], names), settings=False)
    return {f"gcp/{project}": lines} if lines else {}


# ================================================================ writing


def final_names(ix: Index, found: dict[str, dict[str, str]], root: str) -> dict[str, str]:
    """project.provider[.variable], after the project that uses the key most."""
    uses = defaultdict(list)
    for rel, lines in found.items():
        for var, raw in lines.items():
            for _vault, name, _field in tpl.REF.findall(raw):
                uses[name].append((tpl.project(root, rel), var))
    names, taken = {}, set(ix.fixed)
    for old in sorted(uses, key=lambda n: -len(uses[n])):
        if old in ix.fixed:
            continue
        prov = old.split(".")[0]
        top = Counter(p for p, _var in uses[old]).most_common()
        top = sorted(top, key=lambda pc: (-pc[1], pc[0]))[0][0]
        var = Counter(v for _proj, v in uses[old]).most_common(1)[0][0]
        base = f"{top if prov == 'supabase-db' else ix.label.get(old) or top}.{prov}"
        if prov in ("self", "other"):
            base += "." + var
        base = re.sub(r"[^a-z0-9.\-]+", "-", base.lower()).strip("-")
        new, n = base, 2
        while new in taken:
            new, n = f"{base}-{n}", n + 1
        taken.add(new)
        names[old] = new
    return names



def init(ctx, *, vault: str | None, sources: list[str], tags: dict[str, list[str]], retire: list[str],
         paths: list[str] = (), settings: bool = False) -> int:
    """Without paths: every .env file under the root; existing templates are left alone.
    With paths: only those files and folders; existing templates get the variables they lack."""
    vault = vault or next(iter(Counter(v for v, _name in ctx.items()).most_common(1)), (None,))[0]
    if not vault:
        raise RekeyError(_("Say which 1Password vault to use: --vault \"Acme - Prod\""))
    ix = Index(vault)
    ix.seed(ctx)
    step(_("Local .env files"))
    found = from_files(ix, ctx.root, ctx.home, paths, settings)
    ok(_("Files: {n}", n=len(found)))
    for src in sources:
        step(src)
        try:
            if src == "vercel":
                part = from_vercel(ix, ctx, found, ctx.root)
            elif src == "supabase":
                part = from_supabase(ix, ctx)
            elif src == "railway":
                part = from_railway(ix)
            elif src.startswith("gcp:"):
                part = from_gcp(ix, src[4:])
            else:
                raise RekeyError(_("unknown source: {src}", src=src))
            found |= part
            ok(_("Places: {n}", n=len(part)))
        except RekeyError as e:
            fail(f"{src}: {e}")

    for old, new in final_names(ix, found, ctx.root).items():
        ix.notes[new] = ix.notes.pop(old, set())
        for lines in found.values():
            for var, raw in lines.items():
                lines[var] = raw.replace(f"/{old}/", f"/{new}/")

    written = added = 0
    for rel, lines in sorted(found.items()):
        path = os.path.join(ctx.home, "targets", rel + ".tpl")
        text = "".join(v + "\n" if v.startswith("# ") else f"{k}={v}\n" for k, v in lines.items())
        if os.path.exists(path):
            if not paths:
                continue
            with open(path) as f:
                have = f.read()
            have_vars = set(tpl.parse(have, rel).lines)
            new = [line for line in text.splitlines(True) if line.split("=", 1)[0] not in have_vars and line not in have]
            if new:
                with open(path, "a") as f:
                    f.write(("" if have.endswith("\n") or not have else "\n") + "".join(new))
                added += len(new)
                say(f"  + targets/{rel}.tpl  " + dim(_("lines added: {n}", n=len(new))))
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        say(f"  + targets/{rel}.tpl")
        written += 1

    users = defaultdict(set)
    for rel, lines in found.items():
        for raw in lines.values():
            for _vault, name, _field in tpl.REF.findall(raw):
                users[name].add(rel)
    keys_path = os.path.join(ctx.home, "keys.toml")
    have = ""
    if os.path.exists(keys_path):
        with open(keys_path) as f:
            have = f.read()
    blocks = []
    for name in sorted(users):
        if f'["{name}"]' in have:
            continue
        t = sorted(tag for tag, prefixes in tags.items() if any(r.startswith(p) for r in users[name] for p in prefixes))
        notes = ix.notes.get(name, set())
        if retire and all(any(r.startswith(p) for p in retire) for r in users[name]):
            t.append("retire")
        if "legacy" in notes:
            t.append("check")
        entry = []
        if "locked" in notes:
            entry.append(f'locked = "{_(NOTES["locked"])}"')
        note = " ".join(_(NOTES[n]) for n in sorted(notes) if n in NOTES and n != "locked")
        if note:
            entry.append(f'note = "{note}"')
        if t:
            entry.append("tags = [" + ", ".join(f'"{x}"' for x in t) + "]")
        if entry:
            blocks.append(f'["{name}"]\n' + "\n".join(entry) + "\n")
    with open(keys_path, "a") as f:
        f.write("\n".join(blocks))
    ok(_("New templates: {w} · lines added: {a} · keys: {k} · keys.toml entries added: {b}", w=written, a=added, k=len(users), b=len(blocks)))
    say(dim("  " + _("Next: rekey ls · git diff · rekey import all (today's values into 1Password)")))
    return 0
