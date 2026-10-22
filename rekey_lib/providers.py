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
from dataclasses import dataclass
from typing import Any, Callable

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


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M")


def admin_key(ctx, name: str) -> str:
    """Admin keys live next to the keys they manage, as items named rekey.<name>."""
    rec = ctx.read(ctx.vault, f"rekey.{name}")
    if not rec or not rec.fields.get("credential"):
        raise Unavailable(f"관리자 키 rekey.{name} 없음")
    return rec.fields["credential"]


# ================================================================ browser


def from_browser(ctx, item: str, prov: Provider, old: Fields, fields: list[str], hint: str = "", page: str = "",
                 again: Fields | None = None) -> Fields:
    """The person makes the key on the provider's page; rekey takes it from the clipboard.
    `again`: values copied before that turned out wrong — just wait for another copy."""
    if not (ctx.interactive and interactive()):
        raise Skip(f"사람이 발급해야 합니다: {page or prov.page or prov.label}")
    name = f"rekey-{item}-{stamp()}"
    if again is None:
        page = page or prov.page
        set_clipboard(name)
        if hint:
            say(f"    {bold('참고')} {hint}")
        say(f"    페이지에서 새 키를 만드세요. 이름 칸에 ⌘V → {bold(name)}")
        open_url(page)
        say(dim(f"    {page or '(발급 페이지를 모릅니다. keys.toml에 page를 적어 두면 다음부터 열립니다)'}"))
    out: Fields = {}
    for f in fields:
        what = "새 키를" if f == "credential" else f"'{f}' 값을"
        say(f"    ⏳ {what} {bold('복사')}하면 바로 넘어갑니다  " + dim("[s] 건너뛰기  [q] 그만하기"))
        ignore = {name, *old.values(), *out.values(), *(again or {}).values()}
        out[f] = _await_copy(ignore, set(old.values()), prov.form if f == "credential" else "", prov.label)
        ok(f"받았습니다 ({len(out[f])}자)")
    set_clipboard("")
    return out


def _await_copy(ignore: set[str], old: set[str], form: str, label: str) -> str:
    noted: set[str] = set()
    while True:
        value = clipboard()
        if value and value not in ignore and (not form or re.match(form, value)):
            return value
        if value and value not in noted and value not in ignore - old:
            noted.add(value)
            warn("옛 키입니다. 새로 만든 키를 복사하세요." if value in old
                 else f"{label} 키 형식이 아닙니다. 맞으면 Enter, 아니면 다시 복사하세요.")
        if select.select([sys.stdin], [], [], 0.5)[0]:
            cmd = sys.stdin.readline().strip().lower()
            if cmd == "s":
                raise Skip("건너뜀")
            if cmd == "q":
                raise Stop("그만")
            if value and value not in ignore:
                return value


# ================================================================ generated locally


def issue_self(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    return {f: new_secret() for f in (old or {"credential": ""})}, {}


def issue_db_password(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    """Supabase DB password: rekey makes it, the person pastes it in the dashboard."""
    ref = item.split(".", 1)[1]
    if not (ctx.interactive and interactive()):
        raise Skip("Supabase 화면에서 직접 저장해야 합니다")
    pw = new_secret("password")
    set_clipboard(pw)
    open_url(f"https://supabase.com/dashboard/project/{ref}/database/settings")
    say("    열린 페이지에서 Reset database password → ⌘V → 저장 (새 비밀번호는 클립보드에 있음)")
    warn("저장하는 순간 옛 비밀번호는 끊깁니다. 저장 직후 Enter를 누르면 바로 모든 곳을 바꿉니다.")
    input("    저장했으면 Enter › ")
    set_clipboard("")
    return {"password": pw}, {}


# ================================================================ Google Cloud (gcloud)


def _sa(old: Fields) -> dict:
    raw = old.get("credential") or base64.b64decode(old.get("credential_base64", "")).decode(errors="replace")
    try:
        return json.loads(raw)
    except ValueError:
        raise Unavailable("옛 서비스계정 JSON을 읽지 못함")


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
    return f"{sa['client_email']}의 옛 키 삭제"


def _gcp_key(value: str) -> dict:
    name = json.loads(run(["gcloud", "services", "api-keys", "lookup", value, "--format", "json"]).stdout)["name"]
    return json.loads(run(["gcloud", "services", "api-keys", "describe", name, "--format", "json"]).stdout)


def issue_gcp_api_key(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    try:
        key = _gcp_key(old["credential"])
    except (RekeyError, KeyError):
        raise Unavailable("옛 키가 어느 GCP 프로젝트 것인지 찾지 못함")
    cmd = ["gcloud", "services", "api-keys", "create", "--project", key["name"].split("/")[1],
           "--display-name", f"rekey-{item}-{stamp()}", "--format", "json"]
    cmd += [f"--api-target=service={t['service']}" for t in (key.get("restrictions") or {}).get("apiTargets", [])]
    created = json.loads(run(cmd, timeout=120).stdout)
    name = created.get("response", created)["name"]
    value = json.loads(run(["gcloud", "services", "api-keys", "get-key-string", name, "--format", "json"]).stdout)["keyString"]
    return {"credential": value}, {}


def revoke_gcp_api_key(ctx, item: str, old: Fields, meta: dict) -> str:
    run(["gcloud", "services", "api-keys", "delete", _gcp_key(old["credential"])["name"], "-q"], timeout=120)
    return "옛 API 키 삭제"


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
            raise Unavailable("supabase login 필요")
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
    raise Unavailable("옛 키가 어느 Supabase 프로젝트 것인지 찾지 못함")


def issue_supabase(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    ref, _ = _supabase_ref(ctx, old.get("credential", ""))
    k = _supabase(ctx, "POST", f"/v1/projects/{ref}/api-keys?reveal=true",
                  {"type": "secret", "name": re.sub(r"[^a-z0-9_]", "_", f"rekey_{stamp()}")})
    return {"credential": k["api_key"]}, {}


def revoke_supabase(ctx, item: str, old: Fields, meta: dict) -> str:
    ref, k = _supabase_ref(ctx, old["credential"])
    if k.get("type") == "legacy" or old["credential"].startswith("eyJ"):
        return MANUAL + f"레거시 JWT 키는 따로 지울 수 없습니다. 모든 앱이 새 키로 옮겨진 뒤 https://supabase.com/dashboard/project/{ref}/settings/api-keys 에서 Legacy API keys를 끄세요."
    _supabase(ctx, "DELETE", f"/v1/projects/{ref}/api-keys/{k['id']}")
    return f"secret key {k.get('name')} 삭제"


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
    raise Unavailable("옛 키를 OpenAI 조직에서 찾지 못함")


def issue_openai(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    pid, _ = _openai_find(ctx, old.get("credential", ""))
    sa = api("POST", f"https://api.openai.com/v1/organization/projects/{pid}/service_accounts",
             admin_key(ctx, "openai-admin"), {"name": f"rekey-{item}-{stamp()}"})
    return {"credential": sa["api_key"]["value"]}, {}


def revoke_openai(ctx, item: str, old: Fields, meta: dict) -> str:
    pid, k = _openai_find(ctx, old["credential"])
    api("DELETE", f"https://api.openai.com/v1/organization/projects/{pid}/api_keys/{k['id']}", admin_key(ctx, "openai-admin"))
    return f"옛 키 {k.get('redacted_value')} 삭제"


# ================================================================ Anthropic (no create API; revoke with rekey.anthropic-admin)


def revoke_anthropic(ctx, item: str, old: Fields, meta: dict) -> str:
    try:
        tok = admin_key(ctx, "anthropic-admin")
    except Unavailable:
        return MANUAL + "옛 키를 Disable 하세요."
    hdr = {"x-api-key": tok, "anthropic-version": "2023-06-01"}
    status, page = http("GET", "https://api.anthropic.com/v1/organizations/api_keys?limit=1000&status=active", headers=hdr)
    for k in (page or {}).get("data", []) if status < 300 else []:
        if matches_hint(k.get("partial_key_hint", ""), old["credential"]):
            http("POST", f"https://api.anthropic.com/v1/organizations/api_keys/{k['id']}", headers=hdr, body={"status": "inactive"})
            return f"옛 키 {k.get('name')} 비활성화"
    return MANUAL + "옛 키를 찾지 못했습니다. 직접 Disable 하세요."


# ================================================================ Cloudflare (rekey.cloudflare-admin: "API Tokens: Edit")
#
# An R2 key pair is an API token: access_key_id = token id, secret_access_key = sha256(token).


def _cf_token_id(old: Fields) -> str:
    if old.get("access_key_id"):
        return old["access_key_id"]
    status, d = http("GET", "https://api.cloudflare.com/client/v4/user/tokens/verify", headers={"Authorization": f"Bearer {old.get('credential', '')}"})
    if status >= 300:
        raise Unavailable("옛 토큰을 확인할 수 없음")
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
    return "옛 토큰 삭제"


# ================================================================ Resend (rekey.resend-admin: full access)


def issue_resend(ctx, item: str, old: Fields) -> tuple[Fields, dict]:
    k = api("POST", "https://api.resend.com/api-keys", admin_key(ctx, "resend-admin"), {"name": f"rekey-{item}-{stamp()}"})
    return {"credential": k["token"]}, {"key_id": k["id"]}


def revoke_resend(ctx, item: str, old: Fields, meta: dict) -> str:
    if not meta.get("key_id"):
        return MANUAL + "옛 키를 삭제하세요 (다음부터는 자동)."
    api("DELETE", f"https://api.resend.com/api-keys/{meta['key_id']}", admin_key(ctx, "resend-admin"))
    return "옛 키 삭제"


# ================================================================ catalog

P = Provider
PROVIDERS: dict[str, Provider] = {
    "self": P("자체 생성", issue=issue_self),
    "supabase-db": P("Supabase DB 비밀번호", issue=issue_db_password),
    "openai": P("OpenAI", "https://platform.openai.com/api-keys", r"sk-(?!ant-|or-)", issue_openai, revoke_openai,
                "https://api.openai.com/v1/models", admin="openai-admin"),
    "anthropic": P("Anthropic", "https://console.anthropic.com/settings/keys", "sk-ant-", None, revoke_anthropic,
                   "https://api.anthropic.com/v1/models", "x-api-key: {key}"),
    "google-api-key": P("Google API 키", "https://aistudio.google.com/app/apikey", "AIza", issue_gcp_api_key, revoke_gcp_api_key,
                        "https://generativelanguage.googleapis.com/v1beta/models?key={key}", ""),
    "gcp-sa": P("GCP 서비스계정 키", "https://console.cloud.google.com/iam-admin/serviceaccounts", r"\{", issue_gcp_sa, revoke_gcp_sa),
    "supabase": P("Supabase secret key", "https://supabase.com/dashboard/projects", "sb_secret_", issue_supabase, revoke_supabase),
    "cloudflare": P("Cloudflare 토큰", "https://dash.cloudflare.com/profile/api-tokens", "", issue_cloudflare, revoke_cloudflare,
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
    "github": P("GitHub 토큰", "https://github.com/settings/tokens", "(ghp_|github_pat_)"),
    "railway": P("Railway 토큰", "https://railway.com/dashboard"),
    "cloudflare-turn": P("Cloudflare TURN", "https://dash.cloudflare.com/?to=/:account/calls"),
    "slack": P("Slack 앱", "https://api.slack.com/apps"),
    "ncp": P("NAVER Cloud", "https://www.ncloud.com/mypage/manage/authkey"),
    "expo": P("Expo", "https://expo.dev/settings/access-tokens"),
    "supabase-token": P("Supabase 액세스 토큰", "https://supabase.com/dashboard/account/tokens", "sbp_"),
    "fly": P("Fly.io", "https://fly.io/dashboard/personal/tokens"),
    "vercel": P("Vercel", "https://vercel.com/account/settings/tokens"),
    "google-oauth": P("Google OAuth", "https://console.cloud.google.com/apis/credentials", "GOCSPX-"),
    "apple": P("Apple", "https://developer.apple.com/account/resources/authkeys/list"),
    "polar": P("Polar", "https://polar.sh/dashboard"),
    "meta": P("Meta", "https://business.facebook.com/settings/system-users"),
    "trigger": P("Trigger.dev", "https://cloud.trigger.dev/"),
    "other": P("기타"),
}


def provider(item: str) -> Provider:
    return PROVIDERS.get(item.split(".", 1)[0]) or P(item.split(".", 1)[0])


def works(prov: Provider, fields: Fields) -> bool | None:
    """Does the new key work? None when there is no cheap way to tell."""
    if not prov.check or "credential" not in fields:
        return None
    key = fields["credential"]
    name, _, value = prov.header.partition(": ")
    status, _ = http("GET", prov.check.format(key=key), headers={name: value.format(key=key)} if name else {})
    return status < 300
