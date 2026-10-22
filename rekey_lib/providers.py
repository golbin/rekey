"""Providers: how a new key is obtained and how the old one is revoked.

The provider of an item is the part of its name before the first dot:
"openai.shop" → openai. Unknown providers fall back to the browser.

    issue(ctx, item, old)  → (new fields, meta)   by API; raise Unavailable to fall back to the browser
    revoke(ctx, item, old, meta) → message        by API; return MANUAL + text when a person must do it

Browser path: rekey opens the provider's key page, puts a suggested key name on the
clipboard, and continues as soon as the new key is copied.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import select
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from .i18n import _
from .util import (RekeyError, api, bold, dim, http, interactive, new_secret, ok, open_url, private_file,
                   run, say, set_clipboard, clipboard, warn)

Fields = dict[str, str]
MANUAL = "MANUAL: "


class Unavailable(RekeyError):
    """The API path can't run here (no admin key, unknown project...). Use the browser instead."""


class Skip(RekeyError):
    pass


class Stop(RekeyError):
    pass


@dataclass
class Provider:
    label: str
    page: str = ""                     # where a person makes and deletes keys
    form: str = ""                     # regex every new key of this provider starts with
    issue: Callable | None = None
    revoke: Callable | None = None
    check: str = ""                    # GET url that answers 2xx for a working key; {key} is substituted
    header: str = "Authorization: Bearer {key}"
    admin: str = ""                    # issue() needs the admin key item rekey.<admin>
    how: str = ""                      # what to click and which permissions, when it isn't obvious
    locate: Callable | None = None     # (ctx, item, old) -> the exact page for this key, when the API can't help


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M")


def admin_key(ctx, name: str) -> str:
    """Admin keys live next to the keys they manage, as items named rekey.<name>."""
    rec = ctx.read(ctx.vault, f"rekey.{name}")
    if not rec or not rec.fields.get("credential"):
        raise Unavailable(_("no admin key rekey.{name}", name=name))
    return rec.fields["credential"]


# ================================================================ browser


def from_browser(ctx, item: str, prov: Provider, old: Fields, fields: list[str], hint: str = "", page: str = "",
                 again: Fields | None = None) -> Fields:
    """The person makes the key on the provider's page; rekey takes it from the clipboard.
    `again`: values copied before that turned out wrong — just wait for another copy."""
    if not (ctx.interactive and interactive()):
        raise Skip(_("a person has to issue this one:") + f" {page or prov.page or prov.label}")
    name = f"rekey-{item}-{stamp()}"
    if again is None:
        page = page or prov.page
        set_clipboard(name)
        if hint:
            say("    " + bold(_("Note")) + f" {hint}")
        if prov.how:
            say("    " + bold(prov.how))
        tail = next(iter(old.values()), "")[-4:]
        say("    " + _("Give it the same permissions as the old key") + (f" (…{tail})" if len(tail) == 4 else "") + ".")
        say("    " + _("Make a new key on the page. Name field: ⌘V →") + " " + bold(name))
        open_url(page)
        say(dim("    " + (page or _("(no page known for this service: add page = \"…\" in keys.toml and it opens next time)"))))
    out: Fields = {}
    for f in fields:
        what = _("the new key") if f == "credential" else _("the '{field}' value", field=f)
        say("    ⏳ " + _("Copy {what} and rekey moves on at once", what=what) + "  " + dim("[s] " + _("skip") + "  [q] " + _("stop")))
        ignore = {name, *old.values(), *out.values(), *(again or {}).values()}
        out[f] = _await_copy(ignore, set(old.values()), prov.form if f == "credential" else "", prov.label)
        ok(_("got it ({n} characters)", n=len(out[f])))
    set_clipboard("")
    return out


# Without a provider pattern: one token of 16+ characters, not all digits, or a PEM block.
# Rules out what people copy on the way: sign-in codes, emails, names, sentences.
KEYLIKE = re.compile(r"(?!\d+$)\S{16,}|-----BEGIN [\s\S]+-----END [^\n]+-----")


def looks_like_key(value: str, form: str = "") -> bool:
    value = value.strip()
    return bool(re.match(form, value) if form else KEYLIKE.fullmatch(value))


def _await_copy(ignore: set[str], old: set[str], form: str, label: str) -> str:
    noted: set[str] = set()
    while True:
        value = clipboard()
        if value and value not in ignore and looks_like_key(value, form):
            return value
        if value and value not in noted and value not in ignore - old:
            noted.add(value)
            warn(_("That is the old key. Copy the new one.") if value in old
                 else _("That doesn't look like a {label} key. Enter if it is right, otherwise copy again.", label=label))
        if select.select([sys.stdin], [], [], 0.5)[0]:
            cmd = sys.stdin.readline().strip().lower()
            if cmd == "s":
                raise Skip(_("skipped"))
            if cmd == "q":
                raise Stop(_("stopped"))
            if value and value not in ignore:
                return value


# ================================================================ generated locally


def issue_self(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    return {f: new_secret() for f in (old or {"credential": ""})}, {}


def issue_db_password(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    """Supabase DB password: rekey makes it, the person pastes it in the dashboard."""
    ref = item.split(".", 1)[1]
    if not (ctx.interactive and interactive()):
        raise Skip(_("this has to be saved in the Supabase dashboard"))
    pw = new_secret("password")
    set_clipboard(pw)
    open_url(f"https://supabase.com/dashboard/project/{ref}/database/settings")
    say("    " + _("On the page: Reset database password → ⌘V → Save (the new password is on your clipboard)"))
    warn(_("The old password stops working the moment you save. Press Enter right after saving and every place is updated at once."))
    input("    " + _("Saved? Enter") + " › ")
    set_clipboard("")
    return {"password": pw}, {}


# ================================================================ Google Cloud (gcloud)


def _sa(old: Fields) -> dict:
    raw = old.get("credential") or base64.b64decode(old.get("credential_base64", "")).decode(errors="replace")
    try:
        return json.loads(raw)
    except ValueError:
        raise Unavailable(_("can't read the old service account JSON"))


def issue_gcp_sa(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    sa = _sa(old)
    with private_file("", ".json") as path:
        run(["gcloud", "iam", "service-accounts", "keys", "create", path, "--iam-account", sa["client_email"], "--project", sa["project_id"]])
        with open(path) as f:
            value = f.read()
    return {"credential": value, "credential_base64": base64.b64encode(value.encode()).decode()}, {}


def revoke_gcp_sa(ctx, item: str, old: Fields, meta: dict) -> str:
    sa = _sa(old)
    run(["gcloud", "iam", "service-accounts", "keys", "delete", sa["private_key_id"],
         "--iam-account", sa["client_email"], "--project", sa["project_id"], "-q"])
    return _("deleted the old key of {account}", account=sa["client_email"])


def _gcp_key(value: str) -> dict:
    name = json.loads(run(["gcloud", "services", "api-keys", "lookup", value, "--format", "json"]).stdout)["name"]
    return json.loads(run(["gcloud", "services", "api-keys", "describe", name, "--format", "json"]).stdout)


def issue_gcp_api_key(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    try:
        key = _gcp_key(old["credential"])
    except (RekeyError, KeyError):
        raise Unavailable(_("can't tell which GCP project the old key belongs to"))
    cmd = ["gcloud", "services", "api-keys", "create", "--project", key["name"].split("/")[1],
           "--display-name", f"rekey-{item}-{stamp()}", "--format", "json"]
    cmd += [f"--api-target=service={t['service']}" for t in (key.get("restrictions") or {}).get("apiTargets", [])]
    created = json.loads(run(cmd, timeout=120).stdout)
    name = created.get("response", created)["name"]
    value = json.loads(run(["gcloud", "services", "api-keys", "get-key-string", name, "--format", "json"]).stdout)["keyString"]
    return {"credential": value}, {}


def revoke_gcp_api_key(ctx, item: str, old: Fields, meta: dict) -> str:
    run(["gcloud", "services", "api-keys", "delete", _gcp_key(old["credential"])["name"], "-q"], timeout=120)
    return _("deleted the old API key")


# ================================================================ Supabase secret keys (Management API)


def _supabase(ctx, method: str, path: str, body: Any = None) -> Any:
    def token() -> str:
        """The token `supabase login` saved: env var, file (Linux), or the macOS keychain."""
        tok = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
        path = os.path.expanduser("~/.supabase/access-token")
        if not tok and os.path.exists(path):
            with open(path) as f:
                tok = f.read().strip()
        if not tok and sys.platform == "darwin":
            tok = run(["security", "find-generic-password", "-s", "Supabase CLI", "-w"], check=False).stdout.strip()
        if tok.startswith("go-keyring-base64:"):
            tok = base64.b64decode(tok.split(":", 1)[1]).decode()
        if not tok:
            raise Unavailable(_("supabase login needed"))
        return tok
    return api(method, f"https://api.supabase.com{path}", ctx.cached("supabase-token", token), body)


def _supabase_ref(ctx, value: str) -> tuple[str, dict]:
    """The project and key entry that own a key value."""
    data = json.loads(run(["supabase", "projects", "list", "-o", "json"]).stdout)
    for p in data.get("projects", []) if isinstance(data, dict) else data:
        ref = p.get("ref") or p["id"]
        for k in _supabase(ctx, "GET", f"/v1/projects/{ref}/api-keys?reveal=true"):
            if k.get("api_key") == value:
                return ref, k
    raise Unavailable(_("can't tell which Supabase project the old key belongs to"))


def locate_supabase(ctx, item: tuple[str, str], old: Fields) -> str:
    """The project the old key opens, among the Supabase projects the same templates mention."""
    refs = {a or b for t in ctx.users(item) for raw in t.lines.values()
            for a, b in re.findall(r"([a-z]{20})\.supabase\.co|postgres\.([a-z]{20})", raw)}
    key = old.get("credential", "")
    for ref in sorted(refs):
        try:
            status, _body = http("GET", f"https://{ref}.supabase.co/rest/v1/", headers={"apikey": key, "Authorization": f"Bearer {key}"})
        except RekeyError:                     # a project that no longer exists
            continue
        if status < 300:
            return f"https://supabase.com/dashboard/project/{ref}/settings/api-keys"
    return ""


def issue_supabase(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    ref, _key = _supabase_ref(ctx, old.get("credential", ""))
    k = _supabase(ctx, "POST", f"/v1/projects/{ref}/api-keys?reveal=true",
                  {"type": "secret", "name": re.sub(r"[^a-z0-9_]", "_", f"rekey_{stamp()}")})
    return {"credential": k["api_key"]}, {}


def revoke_supabase(ctx, item: str, old: Fields, meta: dict) -> str:
    ref, k = _supabase_ref(ctx, old["credential"])
    if k.get("type") == "legacy" or old["credential"].startswith("eyJ"):
        return MANUAL + _("Legacy JWT keys can't be deleted one by one. Once every app uses the new keys, turn off Legacy API keys at {url}", url=f"https://supabase.com/dashboard/project/{ref}/settings/api-keys")
    _supabase(ctx, "DELETE", f"/v1/projects/{ref}/api-keys/{k['id']}")
    return _("deleted secret key {name}", name=k.get("name"))


# ================================================================ OpenAI (Admin API: rekey.openai-admin)


def matches_hint(hint: str, value: str) -> bool:
    """Admin APIs show keys masked, e.g. 'sk-proj-abc...wxyz' or 'sk-ab****yz'."""
    m = re.fullmatch(r"(.+?)(?:\*+|\.\.\.)(.*)", hint or "")
    return bool(m and value.startswith(m.group(1)) and value.endswith(m.group(2)))



def _openai_find(ctx, value: str) -> tuple[str, dict]:
    tok = admin_key(ctx, "openai-admin")
    for p in api("GET", "https://api.openai.com/v1/organization/projects?limit=100", tok)["data"]:
        for k in api("GET", f"https://api.openai.com/v1/organization/projects/{p['id']}/api_keys?limit=100", tok)["data"]:
            if matches_hint(k.get("redacted_value", ""), value):
                return p["id"], k
    raise Unavailable(_("can't find the old key in the OpenAI organization"))


def issue_openai(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    pid, _key = _openai_find(ctx, old.get("credential", ""))
    sa = api("POST", f"https://api.openai.com/v1/organization/projects/{pid}/service_accounts",
             admin_key(ctx, "openai-admin"), {"name": f"rekey-{item}-{stamp()}"})
    return {"credential": sa["api_key"]["value"]}, {}


def revoke_openai(ctx, item: str, old: Fields, meta: dict) -> str:
    pid, k = _openai_find(ctx, old["credential"])
    api("DELETE", f"https://api.openai.com/v1/organization/projects/{pid}/api_keys/{k['id']}", admin_key(ctx, "openai-admin"))
    return _("deleted the old key {key}", key=k.get("redacted_value"))


# ================================================================ Anthropic (no create API; revoke with rekey.anthropic-admin)


def revoke_anthropic(ctx, item: str, old: Fields, meta: dict) -> str:
    try:
        tok = admin_key(ctx, "anthropic-admin")
    except Unavailable:
        return MANUAL + _("Disable the old key.")
    hdr = {"x-api-key": tok, "anthropic-version": "2023-06-01"}
    status, page = http("GET", "https://api.anthropic.com/v1/organizations/api_keys?limit=1000&status=active", headers=hdr)
    for k in (page or {}).get("data", []) if status < 300 else []:
        if matches_hint(k.get("partial_key_hint", ""), old["credential"]):
            http("POST", f"https://api.anthropic.com/v1/organizations/api_keys/{k['id']}", headers=hdr, body={"status": "inactive"})
            return _("disabled the old key {key}", key=k.get("name"))
    return MANUAL + _("Couldn't find the old key. Disable it yourself.")


# ================================================================ Cloudflare (rekey.cloudflare-admin: "API Tokens: Edit")
#
# An R2 key pair is an API token: access_key_id = token id, secret_access_key = sha256(token).


def _cf_token_id(old: Fields) -> str:
    if old.get("access_key_id"):
        return old["access_key_id"]
    status, d = http("GET", "https://api.cloudflare.com/client/v4/user/tokens/verify", headers={"Authorization": f"Bearer {old.get('credential', '')}"})
    if status >= 300:
        raise Unavailable(_("can't check the old token"))
    return d["result"]["id"]


def _cf(ctx, method: str, path: str, body: Any = None) -> Any:
    return api(method, f"https://api.cloudflare.com/client/v4{path}", admin_key(ctx, "cloudflare-admin"), body)["result"]


def issue_cloudflare(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    import hashlib

    t = _cf(ctx, "GET", f"/user/tokens/{_cf_token_id(old)}")
    new = _cf(ctx, "POST", "/user/tokens", {k: t[k] for k in ("policies", "condition") if t.get(k)} | {"name": f"{t['name']} ({stamp()})"})
    if "access_key_id" in old:
        return {"access_key_id": new["id"], "secret_access_key": hashlib.sha256(new["value"].encode()).hexdigest()}, {}
    return {"credential": new["value"]}, {}


def revoke_cloudflare(ctx, item: str, old: Fields, meta: dict) -> str:
    _cf(ctx, "DELETE", f"/user/tokens/{_cf_token_id(old)}")
    return _("deleted the old token")


# ================================================================ Resend (rekey.resend-admin: full access)


def issue_resend(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    k = api("POST", "https://api.resend.com/api-keys", admin_key(ctx, "resend-admin"), {"name": f"rekey-{item}-{stamp()}"})
    return {"credential": k["token"]}, {"key_id": k["id"]}


def revoke_resend(ctx, item: str, old: Fields, meta: dict) -> str:
    if not meta.get("key_id"):
        return MANUAL + _("Delete the old key (automatic from next time).")
    api("DELETE", f"https://api.resend.com/api-keys/{meta['key_id']}", admin_key(ctx, "resend-admin"))
    return _("deleted the old key")


# ================================================================ catalog

P = Provider
PROVIDERS: dict[str, Provider] = {
    "self": P(_("generated"), issue=issue_self),
    "supabase-db": P(_("Supabase DB password"), issue=issue_db_password),
    "openai": P("OpenAI", "https://platform.openai.com/api-keys", r"sk-(?!ant-|or-)", issue_openai, revoke_openai,
                "https://api.openai.com/v1/models", admin="openai-admin"),
    "anthropic": P("Anthropic", "https://console.anthropic.com/settings/keys", "sk-ant-", None, revoke_anthropic,
                   "https://api.anthropic.com/v1/models", "x-api-key: {key}"),
    "google-api-key": P(_("Google API key"), "https://aistudio.google.com/app/apikey", "AIza", issue_gcp_api_key, revoke_gcp_api_key,
                        "https://generativelanguage.googleapis.com/v1beta/models?key={key}", ""),
    "gcp-sa": P(_("GCP service account key"), "https://console.cloud.google.com/iam-admin/serviceaccounts", r"\{", issue_gcp_sa, revoke_gcp_sa),
    "supabase": P("Supabase secret key", "https://supabase.com/dashboard/projects", "sb_secret_", issue_supabase, revoke_supabase,
                  how="Secret keys → + Add new secret key → copy the sb_secret_… value.", locate=locate_supabase),
    "cloudflare": P(_("Cloudflare token"), "https://dash.cloudflare.com/profile/api-tokens", "", issue_cloudflare, revoke_cloudflare,
                    admin="cloudflare-admin"),
    "resend": P("Resend", "https://resend.com/api-keys", "re_", issue_resend, revoke_resend, admin="resend-admin"),
    "groq": P("Groq", "https://console.groq.com/keys", "gsk_", check="https://api.groq.com/openai/v1/models"),
    "openrouter": P("OpenRouter", "https://openrouter.ai/settings/keys", "sk-or-", check="https://openrouter.ai/api/v1/key"),
    "cartesia": P("Cartesia", "https://play.cartesia.ai/keys"),
    "deepgram": P("Deepgram", "https://console.deepgram.com/"),
    "assemblyai": P("AssemblyAI", "https://www.assemblyai.com/app/api-keys"),
    "elevenlabs": P("ElevenLabs", "https://elevenlabs.io/app/settings/api-keys"),
    "daily": P("Daily", "https://dashboard.daily.co/developers"),
    "heygen": P("HeyGen", "https://app.heygen.com/settings?nav=API"),
    "upstage": P("Upstage", "https://console.upstage.ai/api-keys"),
    "tavily": P("Tavily", "https://app.tavily.com/home", "tvly-"),
    "brave": P("Brave Search", "https://api-dashboard.search.brave.com/app/keys"),
    "sentry": P("Sentry", "https://sentry.io/settings/auth-tokens/", "sntrys_"),
    "github": P(_("GitHub token"), "https://github.com/settings/tokens", "(ghp_|github_pat_)"),
    "railway": P(_("Railway token"), "https://railway.com/dashboard",
                 how="Project → Settings → Tokens → Create, in the same environment as the old token."),
    "cloudflare-turn": P("Cloudflare TURN", "https://dash.cloudflare.com/?to=/:account/realtime/turn",
                         how="Realtime → TURN Server → Create TURN key. Copy the API token first, then the Turn Token ID."),
    "slack": P(_("Slack app"), "https://api.slack.com/apps"),
    "ncp": P("NAVER Cloud", "https://www.ncloud.com/mypage/manage/authkey"),
    "expo": P("Expo", "https://expo.dev/settings/access-tokens"),
    "supabase-token": P(_("Supabase access token"), "https://supabase.com/dashboard/account/tokens", "sbp_"),
    "fly": P("Fly.io", "https://fly.io/dashboard/personal/tokens"),
    "vercel": P("Vercel", "https://vercel.com/account/settings/tokens"),
    "google-oauth": P("Google OAuth", "https://console.cloud.google.com/apis/credentials", "GOCSPX-"),
    "apple": P("Apple", "https://developer.apple.com/account/resources/authkeys/list"),
    "polar": P("Polar", "https://polar.sh/dashboard"),
    "meta": P("Meta", "https://business.facebook.com/settings/system-users"),
    "trigger": P("Trigger.dev", "https://cloud.trigger.dev/"),
    "stripe": P("Stripe", "https://dashboard.stripe.com/apikeys", r"(sk|rk)_(live|test)_"),
    "other": P(_("other")),
}


def provider(item: str) -> Provider:
    return PROVIDERS.get(item.split(".", 1)[0]) or P(item.split(".", 1)[0])


def works(prov: Provider, fields: Fields) -> bool | None:
    """Does the new key work? None when there is no cheap way to tell."""
    if not prov.check or "credential" not in fields:
        return None
    key = fields["credential"]
    name, _sep, value = prov.header.partition(": ")
    for wait in (0, 3, 5, 10, 15):              # a key just made can take a few seconds to start working
        time.sleep(wait)
        status, _body = http("GET", prov.check.format(key=key), headers={name: value.format(key=key)} if name else {})
        if status < 300 or status not in (401, 403):
            break
    return status < 300
