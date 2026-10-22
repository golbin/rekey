"""Templates: one file per place secrets are used, in 1Password's own template syntax.

    targets/<kind>/<address>.tpl

    # comments are fine
    NEXT_PUBLIC_APP_URL=https://shop.example.com                  ← plain setting
    OPENAI_API_KEY={{ op://Acme - Prod/shop.openai/credential }}
    DATABASE_URL=postgresql://postgres.abc:{{ op://Acme - Prod/shop.supabase-db/password }}@host:5432/postgres

The path says where the values go (targets/vercel/shop/production.tpl → Vercel
project "shop", production). Values are written as-is: no quotes in templates.
Only the variables listed are written; anything else at the target is left alone.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

REF = re.compile(r"\{\{\s*op://([^/{}]+)/([^/{}]+)/([^/{}\s]+)\s*\}\}")
LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

Item = tuple[str, str]          # (vault, item name)
Lookup = Callable[[str, str, str], str]   # (vault, item, field) -> value


@dataclass
class Template:
    rel: str                     # e.g. "vercel/shop/production"
    lines: dict[str, str] = field(default_factory=dict)   # VAR -> raw template value

    @property
    def kind(self) -> str:
        return self.rel.split("/", 1)[0]

    @property
    def address(self) -> list[str]:
        return self.rel.split("/")[1:]

    def items(self) -> set[Item]:
        return {(m[0], m[1]) for raw in self.lines.values() for m in REF.findall(raw)}

    def vars_using(self, item: Item) -> list[str]:
        return [var for var, raw in self.lines.items() if any((m[0], m[1]) == item for m in REF.findall(raw))]


def parse(text: str, rel: str) -> Template:
    t = Template(rel)
    for line in text.splitlines():
        m = LINE.match(line.rstrip())
        if m and not line.lstrip().startswith("#"):
            t.lines[m.group(1)] = m.group(2)
    return t


def load(targets_dir: str) -> list[Template]:
    out = []
    for dp, _dirs, fns in os.walk(targets_dir):
        for fn in sorted(fns):
            if fn.endswith(".tpl"):
                path = os.path.join(dp, fn)
                with open(path) as f:
                    out.append(parse(f.read(), os.path.relpath(path, targets_dir)[: -len(".tpl")]))
    return sorted(out, key=lambda t: t.rel)


def resolve(raw: str, lookup: Lookup) -> str:
    return REF.sub(lambda m: lookup(m.group(1), m.group(2), m.group(3)), raw)


def reverse(raw: str, value: str) -> dict[tuple[str, str, str], str] | None:
    """Field values recovered from a resolved value: the inverse of resolve()."""
    refs = REF.findall(raw)
    if not refs:
        return None
    pattern, pos, seen = "", 0, {}
    for m in REF.finditer(raw):
        key = (m.group(1), m.group(2), m.group(3))
        pattern += re.escape(raw[pos:m.start()])
        if key in seen:
            pattern += f"(?P={seen[key]})"
        else:
            seen[key] = f"g{len(seen)}"
            pattern += f"(?P<{seen[key]}>.+?)"
        pos = m.end()
    pattern += re.escape(raw[pos:])
    m = re.fullmatch(pattern, value.strip(), re.S)
    return {key: m.group(g) for key, g in seen.items()} if m else None


def project(root: str, rel: str) -> str:
    """The project a template belongs to: the git repository of a file, a Railway service, a Vercel project…"""
    kind, *a = rel.split("/")
    if kind == "file":
        return next((a[k - 1] for k in range(len(a) - 1, 0, -1) if os.path.exists(os.path.join(root, *a[:k], ".git"))), a[0])
    return a[2] if kind == "railway" and len(a) > 2 else a[1] if kind == "github" and len(a) > 1 else a[0]


def env(rel: str) -> str:
    """Prod, Dev or Local: local files are Local; production targets and secret stores are Prod."""
    kind, *a = rel.split("/")
    name = {"file": "local", "railway": a[1] if len(a) > 1 else "", "vercel": a[-1],
            "github": a[2] if len(a) > 2 else "production"}.get(kind, "production").lower()
    return "Local" if name == "local" else "Prod" if name in ("production", "prod") else "Dev"


def ref(vault: str, item: str, field_name: str = "credential") -> str:
    return "{{ op://%s/%s/%s }}" % (vault, item, field_name)
