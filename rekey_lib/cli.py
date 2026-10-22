"""rekey <command> — see README.md."""

from __future__ import annotations

import argparse
import os
import unicodedata

from collections import Counter

from . import core
from .init import init
from .providers import provider
from .store import open_store
from . import __version__
from .i18n import _
from .util import RekeyError, bold, dim, fail, say

def find_home(start: str | None = None) -> str:
    """The team data folder: REKEY_HOME, else the nearest folder up from here with targets/ or keys.toml,
    else the current folder (where `rekey init` starts a new one)."""
    if os.environ.get("REKEY_HOME"):
        return os.path.expanduser(os.environ["REKEY_HOME"])
    here = start or os.getcwd()
    d = here
    while True:
        if os.path.isdir(os.path.join(d, "targets")) or os.path.isfile(os.path.join(d, "keys.toml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return here
        d = parent


def ctx_for(args) -> core.Ctx:
    return core.Ctx(find_home(), open_store(), dry_run=getattr(args, "dry_run", False), interactive=not args.no_input)


def cmd_ls(args) -> int:
    ctx = ctx_for(args)
    rows = [(_("key"), _("service"), _("issued"), _("places"), _("tags"))]
    for item in ctx.select(args.select or ["all"], args.only):
        m = ctx.meta(item[1])
        tags = m.get("tags", []) + (["locked"] if m.get("locked") else [])
        rows.append((item[1], provider(item[1]).label, {"self": _("auto"), "auto": _("auto"), "admin": _("auto") + "*", "browser": _("browser")}[core.mode(item)],
                     str(len(ctx.users(item))), " ".join(tags)))
    width = lambda s: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    w = [max(width(r[i]) for r in rows) for i in range(5)]
    for n, r in enumerate(rows):
        line = "  ".join(c + " " * (w[i] - width(c)) for i, c in enumerate(r)).rstrip()
        say(bold(line) if n == 0 else line)
    counts = Counter(r[2] for r in rows[1:])
    say(dim("\n" + _("Keys: {n}", n=len(rows) - 1) + " · " + " · ".join(f"{k} {n}" for k, n in counts.items())
            + (" · * " + _("automatic with an admin key, otherwise browser") if counts[_("auto") + "*"] else "")))
    return 0


def cmd_where(args) -> int:
    ctx = ctx_for(args)
    for item in ctx.select(args.select):
        say(bold(item[1]) + dim(f"  op://{item[0]}/{item[1]}  · {provider(item[1]).label}"))
        if note := ctx.meta(item[1]).get("note"):
            say(f"  {note}")
        for t in ctx.users(item):
            say(f"  targets/{t.rel}.tpl  {dim(', '.join(t.vars_using(item)))}")
    return 0


def templates(ctx: core.Ctx, names: list[str]):
    return ctx.templates if names == ["all"] else [ctx.template(n) for n in names]


def cmd_sync(args) -> int:
    ctx = ctx_for(args)
    actions, failures = core.sync(ctx, templates(ctx, args.templates))
    failures += core.deploy(ctx, actions) if args.deploy else []
    return 1 if failures else 0


def cmd_diff(args) -> int:
    ctx = ctx_for(args)
    return core.diff(ctx, templates(ctx, args.templates))


def cmd_rotate(args) -> int:
    ctx = ctx_for(args)
    return core.rotate(ctx, ctx.select(args.select, args.only), force=args.force, redo=args.redo)


def cmd_revoke(args) -> int:
    ctx = ctx_for(args)
    return core.revoke(ctx, ctx.select(args.select, args.only), force=args.force)


def cmd_import(args) -> int:
    ctx = ctx_for(args)
    return core.import_(ctx, ctx.select(args.select or ["all"]))


def cmd_setup(args) -> int:
    from .setup import preflight

    ctx = ctx_for(args)
    return 0 if preflight(ctx, ctx.select(args.select or ["all"])) else 1


def cmd_init(args) -> int:
    ctx = ctx_for(args)
    split = lambda specs: {n: p.split(",") for n, _, p in (s.partition("=") for s in specs)}
    return init(ctx, vault=args.vault, sources=args.source, tags=split(args.tag), retire=args.retire.split(",") if args.retire else [],
                group_dirs=[d for d in args.group_dirs.split(",") if d], paths=args.paths, settings=args.with_settings)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rekey", description=_("Reissue, rotate and revoke API keys in one go. See README.md"))
    ap.add_argument("--version", action="version", version=f"rekey {__version__}")
    ap.add_argument("--no-input", action="store_true", help=_("skip steps that need a person and only say what is left"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sel = _("key name or glob, tag:<tag>, in:<template glob>, all")

    def cmd(name, fn, help_, *args):
        p = sub.add_parser(name, help=help_)
        for a in args:
            p.add_argument(*a[0], **a[1])
        p.set_defaults(fn=fn)

    only = (["--only"], {"action": "append", "metavar": "SELECT", "help": _("narrow down: also match this (a service like openai, a name glob, tag:, in:); repeatable")})
    dry = (["--dry-run"], {"action": "store_true", "help": _("show what would happen, change nothing")})
    cmd("ls", cmd_ls, _("list keys"), (["select"], {"nargs": "*", "help": sel}), only)
    cmd("where", cmd_where, _("where a key is used"), (["select"], {"nargs": "+", "help": sel}))
    cmd("rotate", cmd_rotate, _("new key → 1Password → every place → redeploy"), (["select"], {"nargs": "+", "help": sel}), only, dry,
        (["--force"], {"action": "store_true", "help": _("include locked keys and keys tagged check")}),
        (["--redo"], {"action": "store_true", "help": _("make the new key again; the original old key stays the one to revoke")}))
    cmd("revoke", cmd_revoke, _("revoke old keys"), (["select"], {"nargs": "+", "help": sel}), only, dry,
        (["--force"], {"action": "store_true", "help": _("even if the old value is still in use")}))
    cmd("sync", cmd_sync, _("write templates to their targets (settings, a new machine's .env)"), (["templates"], {"nargs": "+", "help": _("template paths, or all")}),
        dry, (["--deploy"], {"action": "store_true", "help": _("redeploy after writing")}))
    cmd("diff", cmd_diff, _("compare templates with what is live"), (["templates"], {"nargs": "+"}))
    cmd("import", cmd_import, _("store the values in use today in 1Password (no rotation)"), (["select"], {"nargs": "*", "help": sel}), dry)
    cmd("setup", cmd_setup, _("check readiness and fix what is missing"), (["select"], {"nargs": "*", "help": sel}))
    cmd("init", cmd_init, _("write templates from today's .env files and platforms (existing files are kept)"),
        (["paths"], {"nargs": "*", "help": _("only these .env files or folders (default: everything under the root)")}),
        (["--vault"], {"help": _("1Password vault for new keys (default: the one your templates use)")}),
        (["--with-settings"], {"action": "store_true", "help": _("also put plain settings of local .env files in the templates")}),
        (["--source"], {"action": "append", "default": [], "help": "vercel · supabase · railway · gcp:<project>"}),
        (["--tag"], {"action": "append", "default": [], "help": _("tag=template path prefix,...")}),
        (["--retire"], {"default": "", "help": _("template path prefixes of places no longer used,...")}),
        (["--group-dirs"], {"default": "", "help": _("folders that hold several projects,... (keys are named after the folders inside)")}))
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (RekeyError, OSError) as e:
        fail(str(e))
        if args.cmd in ("rotate", "revoke", "sync", "import"):
            say(dim(_("Fix the cause and run the same command again: it continues with what is left.")))
        return 2
    except KeyboardInterrupt:
        say("\n" + _("Stopped. Run the same command again to continue with what is left."))
        return 130
