"""Preflight: everything a run needs is checked — and fixed on the spot — before any key
is issued, so a run never stops with half the places on a new key."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter

from .providers import Provider, Skip, from_browser
from .store import Record
from .targets import KINDS, logged_in
from .util import ask, bold, fail, interactive, ok, run, say, step, succeeds

# Logins needed by the API paths of some providers (beyond the target kinds).
PROVIDER_LOGIN = {"gcp-sa": "gcp", "google-api-key": "gcp", "supabase": "supabase"}

# Admin keys that turn a provider's browser steps into API calls. Offered when they save 2+ trips.
ADMIN = {
    "openai": ("openai-admin", "https://platform.openai.com/settings/organization/admin-keys", "sk-admin-",
               "Create new admin key"),
    "cloudflare": ("cloudflare-admin", "https://dash.cloudflare.com/profile/api-tokens", "",
                   "Create Token → Custom → 권한 'User · API Tokens · Edit'"),
    "resend": ("resend-admin", "https://resend.com/api-keys", "re_", "Create API Key → Full access"),
    "anthropic": ("anthropic-admin", "https://console.anthropic.com/settings/admin-keys", "sk-ant-admin",
                  "Create Admin Key (옛 키 자동 폐기용)"),
}


def preflight(ctx, items: list[tuple[str, str]], fix: bool = True) -> bool:
    fix = fix and ctx.interactive and interactive()
    step("준비 점검")
    good = True

    while msg := ctx.store.check():
        fail(msg)
        if not fix:
            good = False
            break
        if sys.platform == "darwin":
            run(["open", "-a", "1Password"], check=False)
        if input("    켰으면 Enter (그만: q) › ").strip().lower() == "q":
            return False
    else:
        ok(ctx.store.label)
        for vault in sorted({v for v, _ in items}):
            if ctx.store.has_vault(vault):
                continue
            fail(f"vault '{vault}' 없음 (또는 권한 없음)")
            if fix and ask(f"    지금 만들까요? (팀원이면 N → 관리자에게 권한 요청)"):
                ctx.store.create_vault(vault)
                ok(f"vault '{vault}' 생성")
            else:
                good = False

    needed = {t.kind for i in items for t in ctx.users(i)} | {PROVIDER_LOGIN.get(n.split(".")[0], "") for _, n in items}
    for name in sorted(needed & set(KINDS)):
        if logged_in(name):
            continue
        check, login = KINDS[name].login
        fail(f"{name} 로그인 필요")
        if fix and ask(f"    `{' '.join(login)}` 실행할까요? (브라우저에서 승인)"):
            subprocess.run(login)
            if succeeds(check):
                ok(f"{name} 로그인")
                continue
        good = False

    if good and fix:
        offer_admin_keys(ctx, items)
    if not good:
        say(bold("\n위 항목을 해결해야 시작할 수 있습니다. 아무것도 바뀌지 않았습니다."))
    return good


def offer_admin_keys(ctx, items: list[tuple[str, str]]) -> None:
    vault = Counter(v for v, _ in items).most_common(1)[0][0]
    for prov, n in Counter(name.split(".")[0] for _, name in items).items():
        if prov not in ADMIN or n < 2:
            continue
        name, page, prefix, how = ADMIN[prov]
        if (rec := ctx.read(vault, f"rekey.{name}")) and rec.fields:
            continue
        say(f"\n  {bold(prov)} 키 {n}개를 자동으로 처리하려면 관리자 키 하나가 필요합니다 ({how}).")
        if not ask("    지금 등록할까요? (N이면 하나씩 브라우저에서)"):
            continue
        try:
            value = from_browser(ctx, f"rekey.{name}", Provider(name, page, prefix), {}, ["credential"])
        except Skip:
            continue
        rec = Record(value)
        rec.stamp()
        ctx.write(vault, f"rekey.{name}", rec)
        ok(f"rekey.{name} 저장")
