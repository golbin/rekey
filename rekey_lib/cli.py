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
from .util import RekeyError, bold, dim, fail, say

HOME = os.environ.get("REKEY_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ctx_for(args) -> core.Ctx:
    return core.Ctx(HOME, open_store(), dry_run=getattr(args, "dry_run", False), interactive=not args.no_input)


def cmd_ls(args) -> int:
    ctx = ctx_for(args)
    rows = [("키", "서비스", "발급", "사용처", "태그")]
    for item in ctx.select(args.select or ["all"]):
        m = ctx.meta(item[1])
        tags = m.get("tags", []) + (["locked"] if m.get("locked") else [])
        rows.append((item[1], provider(item[1]).label, {"self": "자동", "auto": "자동", "admin": "자동*", "browser": "브라우저"}[core.mode(item)],
                     str(len(ctx.users(item))), " ".join(tags)))
    width = lambda s: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    w = [max(width(r[i]) for r in rows) for i in range(5)]
    for n, r in enumerate(rows):
        line = "  ".join(c + " " * (w[i] - width(c)) for i, c in enumerate(r)).rstrip()
        say(bold(line) if n == 0 else line)
    counts = Counter(r[2] for r in rows[1:])
    say(dim(f"\n{len(rows) - 1}개 · " + " · ".join(f"{k} {n}" for k, n in counts.items())
            + (" · * 관리자 키가 있으면 자동, 없으면 브라우저" if counts["자동*"] else "")))
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
    return core.rotate(ctx, ctx.select(args.select), force=args.force)


def cmd_revoke(args) -> int:
    ctx = ctx_for(args)
    return core.revoke(ctx, ctx.select(args.select), force=args.force)


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
                group_dirs=[d for d in args.group_dirs.split(",") if d])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rekey", description="키를 한 번에 재발급·교체·폐기합니다. 자세한 내용은 README.md")
    ap.add_argument("--no-input", action="store_true", help="사람이 필요한 단계는 건너뛰고 안내만")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sel = "키 이름·glob, tag:<태그>, in:<템플릿 glob>, all"

    def cmd(name, fn, help_, *args):
        p = sub.add_parser(name, help=help_)
        for a in args:
            p.add_argument(*a[0], **a[1])
        p.set_defaults(fn=fn)

    dry = (["--dry-run"], {"action": "store_true", "help": "아무것도 바꾸지 않고 보여 주기"})
    cmd("ls", cmd_ls, "키 목록", (["select"], {"nargs": "*", "help": sel}))
    cmd("where", cmd_where, "키가 쓰이는 곳", (["select"], {"nargs": "+", "help": sel}))
    cmd("rotate", cmd_rotate, "새 키 발급 → 1Password → 모든 사용처 → 재배포", (["select"], {"nargs": "+", "help": sel}), dry,
        (["--force"], {"action": "store_true", "help": "잠긴 키(locked)·확인 필요 키(check)도"}))
    cmd("revoke", cmd_revoke, "옛 키 폐기", (["select"], {"nargs": "+", "help": sel}), dry,
        (["--force"], {"action": "store_true", "help": "옛 값을 아직 쓰는 곳이 있어도"}))
    cmd("sync", cmd_sync, "템플릿을 대상에 반영 (설정 변경, 새 PC의 .env 만들기)", (["templates"], {"nargs": "+", "help": "템플릿 경로 또는 all"}),
        dry, (["--deploy"], {"action": "store_true", "help": "반영 후 재배포"}))
    cmd("diff", cmd_diff, "템플릿과 대상의 실제 값 비교", (["templates"], {"nargs": "+"}))
    cmd("import", cmd_import, "지금 쓰는 값을 1Password에 등록 (교체 없이)", (["select"], {"nargs": "*", "help": sel}), dry)
    cmd("setup", cmd_setup, "준비 점검 (빠진 것은 바로 해결)", (["select"], {"nargs": "*", "help": sel}))
    cmd("init", cmd_init, "지금 있는 .env·플랫폼에서 템플릿 만들기 (있는 파일은 그대로)",
        (["--vault"], {"required": True}),
        (["--source"], {"action": "append", "default": [], "help": "vercel · supabase · railway · gcp:<project>"}),
        (["--tag"], {"action": "append", "default": [], "help": "태그=템플릿경로접두어,..."}),
        (["--retire"], {"default": "", "help": "안 쓰는 곳의 템플릿 경로 접두어,..."}),
        (["--group-dirs"], {"default": "", "help": "여러 프로젝트를 담은 폴더 이름,... (키 이름을 그 아래 폴더로 짓기)"}))
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (RekeyError, OSError) as e:
        fail(str(e))
        say(dim("원인을 해결하고 같은 명령을 다시 실행하면 남은 것부터 이어 갑니다."))
        return 2
    except KeyboardInterrupt:
        say("\n중단했습니다. 같은 명령을 다시 실행하면 남은 것부터 이어 갑니다.")
        return 130
