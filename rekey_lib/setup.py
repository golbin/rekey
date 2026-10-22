"""Preflight: everything a run needs is checked — and fixed on the spot — before any key
is issued, so a run never stops with half the places on a new key."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter

from .providers import Provider, Skip, from_browser
from .store import Record
from .targets import KINDS, logged_in
from .i18n import _
from .util import ask, bold, fail, interactive, ok, run, say, step, succeeds

# Logins needed by the API paths of some providers (beyond the target kinds).
PROVIDER_LOGIN = {"gcp-sa": "gcp", "google-api-key": "gcp", "supabase": "supabase"}

# Admin keys that turn a provider's browser steps into API calls. Offered when they save 2+ trips.
ADMIN = {
    "openai": ("openai-admin", "https://platform.openai.com/settings/organization/admin-keys", "sk-admin-",
               "Create new admin key"),
    "cloudflare": ("cloudflare-admin", "https://dash.cloudflare.com/profile/api-tokens", "",
                   "Create Token → Custom → permission 'User · API Tokens · Edit'"),
    "resend": ("resend-admin", "https://resend.com/api-keys", "re_", "Create API Key → Full access"),
    "anthropic": ("anthropic-admin", "https://console.anthropic.com/settings/admin-keys", "sk-ant-admin",
                  "Create Admin Key (to revoke old keys automatically)"),
}


def preflight(ctx, items: list[tuple[str, str]], fix: bool = True) -> bool:
    fix = fix and ctx.interactive and interactive()
    step(_("Preflight"))
    good = True

    while msg := ctx.store.check():
        fail(msg)
        if not fix:
            good = False
            break
        if sys.platform == "darwin":
            run(["open", "-a", "1Password"], check=False)
        if input("    " + _("Turned it on? Enter (stop: q)") + " › ").strip().lower() == "q":
            return False
    else:
        ok(ctx.store.label)
        for vault in sorted({v for v, _name in items}):
            if ctx.store.has_vault(vault):
                continue
            fail(_("vault '{vault}' not found (or no access)", vault=vault))
            if fix and ask("    " + _("Create it now? (If you are joining a team, answer N and ask an admin for access)")):
                ctx.store.create_vault(vault)
                ok(_("vault '{vault}' created", vault=vault))
            else:
                good = False

    needed = {t.kind for i in items for t in ctx.users(i)} | {PROVIDER_LOGIN.get(n.split(".")[0], "") for _vault, n in items}
    for name in sorted(needed & set(KINDS)):
        if logged_in(name):
            continue
        check, login = KINDS[name].login
        fail(_("{name}: login needed", name=name))
        if fix and ask("    " + _("Run `{cmd}`? (approve in the browser)", cmd=' '.join(login))):
            subprocess.run(login)
            if succeeds(check):
                ok(_("{name}: logged in", name=name))
                continue
        good = False

    if good and fix:
        offer_admin_keys(ctx, items)
    if not good:
        say(bold("\n" + _("Fix the items above to start. Nothing was changed.")))
    return good


def offer_admin_keys(ctx, items: list[tuple[str, str]]) -> None:
    vault = Counter(v for v, _name in items).most_common(1)[0][0]
    for prov, n in Counter(name.split(".")[0] for _vault, name in items).items():
        if prov not in ADMIN or n < 2:
            continue
        name, page, prefix, how = ADMIN[prov]
        if (rec := ctx.read(vault, f"rekey.{name}")) and rec.fields:
            continue
        say("\n  " + _("One admin key makes the {prov} keys ({n}) automatic ({how}).", n=n, prov=bold(prov), how=how))
        if not ask("    " + _("Add it now? (N: one by one in the browser)")):
            continue
        try:
            value = from_browser(ctx, name, Provider(name, page, prefix), {}, ["credential"])
        except Skip:
            continue
        rec = Record(value)
        rec.stamp()
        ctx.write(vault, f"rekey.{name}", rec)
        ok(_("rekey.{name} saved", name=name))
