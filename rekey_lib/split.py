"""`rekey split`: one key per project, so a leaked key points at one project and only that one changes.

Only the templates (and keys.toml) change. The values stay where they are: each new name starts with
today's shared value, and the next `rekey rotate` gives every project its own key.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict

from .i18n import _
from .util import bold, dim, ok, say


# Keys that must stay one value everywhere: our own services check each other with it (self), a database
# has one password, data is encrypted with it (locked), or the service gives an account only one key.
KEEP = {"self", "supabase-db", "heygen", "daily", "simli"}


def env_of(rel: str) -> str:
    kind, *addr = rel.split("/")
    env = {"file": "local", "railway": addr[1] if len(addr) > 1 else "", "vercel": addr[-1],
           "github": addr[2] if len(addr) > 2 else "prod", "gcp": "prod", "supabase": "prod"}.get(kind, "")
    return {"production": "prod", "development": "dev"}.get(env.lower(), env.lower())


def split(ctx, items: list[tuple[str, str]]) -> int:
    taken = {name for _vault, name in ctx.items()}
    blocks, made = [], 0
    for vault, name in items:
        if name.split(".")[0] in KEEP or ctx.meta(name).get("locked"):
            continue
        rec = ctx.read(vault, name)
        if rec and rec.state.get("revoke") is not None:
            say(dim("  " + _("{key}: rotated already, left as it is (revoke it first)", key=name)))
            continue
        groups = defaultdict(list)
        for t in ctx.users((vault, name)):
            groups[ctx.project(t.rel)].append(t)
        if len(groups) < 2:
            continue
        prov, project, *purpose = name.split(".")
        keep = max(sorted(groups), key=lambda p: (p == project, len(groups[p])))   # this project keeps the name
        say(bold(name) + dim(f"  {keep}"))
        for proj in sorted(groups):
            if proj == keep:
                continue
            base = ".".join([prov, re.sub(r"[^a-z0-9\-]+", "-", proj.lower()).strip("-"), *purpose])
            envs = {env_of(t.rel) for t in groups[proj]}
            new, n = base, 2
            if new in taken and len(envs) == 1 and (alt := f"{base}-{envs.pop()}") not in taken:
                new = alt                                  # shop.openai exists: shop.openai-prod
            while new in taken:
                new, n = f"{base}-{n}", n + 1
            taken.add(new)
            for t in groups[proj]:
                path = os.path.join(ctx.home, "targets", t.rel + ".tpl")
                with open(path) as f:
                    text = f.read()
                with open(path, "w") as f:
                    f.write(text.replace(f"op://{vault}/{name}/", f"op://{vault}/{new}/"))
            if meta := ctx.meta(name):
                blocks.append(f'["{new}"]\n' + "".join(f"{k} = {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items()))
            say(f"  → {new}" + dim("  " + ", ".join(t.rel for t in groups[proj])))
            made += 1
    if blocks:
        with open(os.path.join(ctx.home, "keys.toml"), "a") as f:
            f.write("\n" + "\n".join(blocks))
    ok(_("New keys: {n}. Give each its own value with rekey rotate (git diff to review)", n=made))
    return 0
