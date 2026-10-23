"""`rekey arrange "Acme - {env}"`: one vault per environment, one key per project, names that say what a key is.

Each key moves to the vault of the environment that uses it (Prod, Dev, Local) and is named
<project>.<service>: shop.openai in "Acme - Prod" is the production OpenAI key of shop. A key shared by
several projects or environments is split, one per project and environment; until the next
`rekey rotate` the pieces hold the same value. Kept whole (in the most protected vault that uses them):
our own service-to-service tokens, database passwords, locked keys, and keys rotated but not yet revoked.
1Password items are moved and renamed, never deleted.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict

from . import tpl
from .i18n import _
from .util import ask, dim, interactive, ok, say, step

RANK = {"Prod": 0, "Dev": 1, "Local": 2}
WHOLE = {"self", "supabase-db"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse(name: str, old_names: bool) -> tuple[str, str, list[str]]:
    """(project, service, purpose). old_names: the earlier <service>.<project>[.<purpose>] order."""
    a, *rest = name.split(".")
    if old_names:
        return (rest[0] if rest else ""), a, rest[1:]
    return (a, rest[0], rest[1:]) if rest else ("", a, [])


def plan(ctx, pattern: str, old_names: bool = False) -> list[tuple[tuple[str, str], tuple[str, str], list, bool]]:
    """(old item, new item, templates, carries the 1Password record) for every key."""
    out, taken = [], set()
    for item in sorted(ctx.items(), key=lambda i: i[1]):
        vault, name = item
        users = ctx.users(item)
        _project, svc, purpose = parse(name, old_names)
        rec = ctx.read(vault, name)
        whole = svc in WHOLE or ctx.meta(item).get("locked") or (rec and rec.state.get("revoke") is not None)
        groups = defaultdict(list)
        for t in users:
            groups[None if whole else (tpl.env(t.target), ctx.project(t))].append(t)
        if None in groups:
            projects = Counter(ctx.project(t) for t in users)
            groups = {(min((tpl.env(t.target) for t in users), key=RANK.get), projects.most_common(1)[0][0]): users}
        first = min(groups, key=lambda g: (RANK[g[0]], g[1]))
        for (env, where), ts in sorted(groups.items(), key=lambda g: (RANK[g[0][0]], g[0][1])):
            new_vault = pattern.format(env=env)
            var = Counter(v for t in ts for v in t.vars_using(item)).most_common(1)[0][0]
            base = ".".join([slug(where), svc, *(purpose if svc in ("self", "other") else [])])
            new = base if (new_vault, base) not in taken else f"{base}.{slug(var)}"
            n = 2
            while (new_vault, new) in taken:
                new, n = f"{base}-{n}", n + 1
            taken.add((new_vault, new))
            out.append((item, (new_vault, new), ts, bool(rec) and (env, where) == first))
    return out


def arrange(ctx, pattern: str, old_names: bool = False) -> int:
    if "{env}" not in pattern:
        say(_("Put {{env}} in the vault name, e.g. \"Acme - {{env}}\""))
        return 1
    moves = plan(ctx, pattern, old_names)
    changed = [m for m in moves if m[0] != m[1]]
    flat = [t for t in ctx.templates if t.group is None]
    for vault in sorted({nv for _o, (nv, _n), _t, _r in moves}):
        step(vault)
        for (ov, on), (nv, nn), ts, carries in moves:
            if nv == vault and ((ov, on) != (nv, nn)):
                say(f"  {nn}" + dim(f"  ← {on}" + (" · 1Password" if carries else "") + "  " + ", ".join(t.rel for t in ts)))
    say("\n" + _("Keys renamed or moved: {n}", n=len(changed)))
    if flat:
        say(_("Templates moved into project folders: {n}", n=len(flat)) + dim("  e.g. targets/" + ctx.project(flat[0]) + "/" + flat[0].rel + ".tpl"))
    if ctx.dry_run or not (changed or flat):
        return 0
    if ctx.interactive and interactive() and not ask(_("Apply? Templates, keys.toml and 1Password items change (nothing is deleted)"), default=False):
        return 0

    for vault in sorted({nv for _o, (nv, _n), _t, _r in changed}):
        if not ctx.store.has_vault(vault):
            ctx.store.create_vault(vault)
            ok(_("vault '{vault}' created", vault=vault))
    # Ids first, while every name is still unique; then rename and move by id.
    ids = {(ov, on): ctx.store.item_id(ov, on) for (ov, on), _n, _t, carries in changed if carries}
    for (ov, on), (nv, nn), _ts, carries in changed:
        if carries:
            ctx.store.move(ov, ids[(ov, on)], nv, nn)
    # One pass per template, so a new name that equals another key's old name is never renamed twice.
    renames: dict[str, dict[tuple[str, str], tuple[str, str]]] = defaultdict(dict)
    for old, new, ts, _carries in changed:
        for t in ts:
            renames[t.rel][old] = new
    for rel, mapping in renames.items():
        path = os.path.join(ctx.home, "targets", rel + ".tpl")
        with open(path) as f:
            text = f.read()
        swap = lambda m: "op://{}/{}/".format(*mapping.get((m[1], m[2]), (m[1], m[2])))
        with open(path, "w") as f:
            f.write(re.sub(r"op://([^/{}]+)/([^/{}]+)/", swap, text))
    # Templates into project folders: targets/<project>/<kind>/<address>.tpl
    for t in ctx.templates:
        if t.group is None:
            os.renames(os.path.join(ctx.home, "targets", t.rel + ".tpl"),
                       os.path.join(ctx.home, "targets", ctx.project(t), t.rel + ".tpl"))
    # keys.toml, rebuilt: each new key gets the notes and tags of the key it came from. An entry is
    # ["name"], or ["Vault/name"] when the same name in another vault needs something different.
    per_item: dict[tuple[str, str], dict] = {}
    for old, new, _t, _r in moves:
        for k, v in ctx.meta(old).items():
            m = per_item.setdefault(new, {})
            m[k] = sorted(set(m.get(k, [])) | set(v)) if k == "tags" else m.get(k, v)
    vaults_of = defaultdict(set)
    for _o, (nv, nn), _t, _r in moves:
        vaults_of[nn].add(nv)
    used = {o[1] for o, _n, _t, _r in moves} | {f"{o[0]}/{o[1]}" for o, _n, _t, _r in moves}
    merged = {n: dict(m) for n, m in ctx.keys.items() if n not in used}      # entries for keys no template uses
    for (nv, nn), m in per_item.items():
        same = all(per_item.get((v, nn)) == m for v in vaults_of[nn])
        merged[nn if same else f"{nv}/{nn}"] = m
    keys_path = os.path.join(ctx.home, "keys.toml")
    head = ""
    if os.path.exists(keys_path):
        with open(keys_path) as f:
            head = f.read().split("[", 1)[0]          # comments above the first entry stay
    with open(keys_path, "w") as f:
        f.write(head + "\n".join(f'["{n}"]\n' + "".join(f"{k} = {json.dumps(v, ensure_ascii=False)}\n" for k, v in m.items())
                                for n, m in sorted(merged.items())))
    ok(_("Done. Review with git diff, then commit."))
    return 0
