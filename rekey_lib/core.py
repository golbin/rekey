"""The operations. Everything is derived from two plain-text sources:

    targets/**.tpl   where each key is used (and plain settings)   — git
    keys.toml        exceptions only: tags, notes, locked, page    — git
and the values in 1Password.
"""

from __future__ import annotations

import fnmatch
import os
import re
import time
import tomllib
from collections import Counter
from typing import Any, Callable

from . import tpl
from .providers import MANUAL, Skip, Stop, Unavailable, admin_record, from_browser, key_name, provider, service, works
from .store import Record
from .targets import BROKEN, DEPLOY, HEALTHY, kind
from .i18n import _
from .util import RekeyError, ask, bold, dim, fail, interactive, ok, open_url, say, step, warn

Item = tpl.Item


class Ctx:
    def __init__(self, home: str, store, *, dry_run: bool = False, interactive: bool = True):
        self.home = home
        self.root = os.path.expanduser(os.environ.get("REKEY_ROOT") or os.path.dirname(home))
        self.store = store
        self.dry_run = dry_run
        self.interactive = interactive
        self.templates = tpl.load(os.path.join(home, "targets"))
        self.keys: dict[str, dict[str, Any]] = {}
        if os.path.exists(path := os.path.join(home, "keys.toml")):
            with open(path, "rb") as f:
                self.keys = tomllib.load(f)
        self.vault = ""
        self._cache: dict[str, Any] = {}

    def cached(self, key: str, make: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    # -- values
    def read(self, vault: str, name: str) -> Record | None:
        if f"vault:{vault}" not in self._cache:          # the whole vault in one go: one op call, not one per key
            say(dim("  " + _("Reading the keys in '{vault}'…", vault=vault)))
            try:
                recs = self.store.read_all(vault)
            except RekeyError:
                recs = None
            self._cache[f"vault:{vault}"] = recs is not None
            for n, rec in (recs or {}).items():
                self._cache[f"rec:{vault}/{n}"] = rec
        if self._cache[f"vault:{vault}"]:
            return self._cache.get(f"rec:{vault}/{name}")
        return self.cached(f"rec:{vault}/{name}", lambda: self.store.read(vault, name))

    def write(self, vault: str, name: str, rec: Record) -> None:
        self.store.write(vault, name, rec, self.meta((vault, name)).get("tags", []))
        self._cache[f"rec:{vault}/{name}"] = rec

    def lookup(self, vault: str, name: str, field: str) -> str:
        rec = self.read(vault, name)
        if not rec or field not in rec.fields:
            raise RekeyError(_("{name} is not in {store} '{vault}'. Check your vault access (adopting rekey? rekey import {name})", name=name, store=self.store.label, vault=vault))
        return rec.fields[field]

    # -- structure
    def items(self) -> list[Item]:
        return sorted({i for t in self.templates for i in t.items()}, key=lambda i: i[1])

    def users(self, item: Item) -> list[tpl.Template]:
        return [t for t in self.templates if item in t.items()]

    def fields(self, item: Item) -> list[str]:
        return sorted({f for t in self.users(item) for raw in t.lines.values()
                       for v, n, f in tpl.REF.findall(raw) if (v, n) == item})

    def meta(self, item: Item | str) -> dict[str, Any]:
        """keys.toml entry: ["Vault/name"] for one vault, else ["name"]."""
        if isinstance(item, str):
            return self.keys.get(item, {})
        return self.keys.get(f"{item[0]}/{item[1]}") or self.keys.get(item[1], {})

    def project(self, t: tpl.Template) -> str:
        """The folder the template sits in; else guessed from the target (tpl.project). A Supabase project ref
        takes the name of the project whose templates point at it."""
        if t.group:
            return t.group
        if t.kind != "supabase":
            return tpl.project(self.root, t.target)
        ref = t.address[0]
        def find() -> str:
            named = Counter(self.project(o) for o in self.templates
                            if o.kind != "supabase" and any(ref in raw for raw in o.lines.values()))
            return named.most_common(1)[0][0] if named else ref
        return self.cached("project:" + ref, find)

    def select(self, selectors: list[str], only: list[str] | None = None) -> list[Item]:
        """name or glob · tag:<tag> · in:<template glob> · project:<name> · all. Items tagged 'retire' only by name.
        `only`: narrow down; a bare word means that service or project (openai, shop)."""
        out = []
        for item in self.items():
            name, m = item[1], self.meta(item)
            for sel in selectors:
                kind_, _sep, arg = sel.partition(":")
                hit = (sel == "all" and "retire" not in m.get("tags", [])) \
                    or (kind_ == "tag" and arg in m.get("tags", [])) \
                    or (kind_ == "in" and any(fnmatch.fnmatch(t.target, arg) or fnmatch.fnmatch(t.rel, arg) for t in self.users(item))) \
                    or (kind_ == "project" and any(fnmatch.fnmatch(self.project(t), arg) for t in self.users(item))) \
                    or fnmatch.fnmatch(name, sel)
                if hit:
                    out.append(item)
                    break
        if only:
            bare = lambda g: [f"{g}.*", f"*.{g}", f"*.{g}.*"]      # shop.openai, shop.self.x: by project or service
            keep = set(self.select([s for g in only for s in ([g] if ":" in g or any(c in g for c in ".*?[") else bare(g))]))
            out = [i for i in out if i in keep]
        if not self.templates:
            raise RekeyError(_("No templates in {home}. Run rekey inside your team data folder, or start one there with rekey init.", home=self.home))
        if not out:
            raise RekeyError(_("No keys match {sel} (rekey ls)", sel=" ".join(selectors + [f"--only {g}" for g in only or []])))
        return out

    def template(self, rel: str) -> tpl.Template:
        rel = rel.removeprefix("targets/").removesuffix(".tpl")
        for t in self.templates:
            if rel in (t.rel, t.target):
                return t
        raise RekeyError(_("No such template: targets/{rel}.tpl", rel=rel))


def mode(item: Item, ctx: Ctx | None = None) -> str:
    """self · auto · admin (auto when the admin key exists) · browser. With ctx, 'admin' is resolved."""
    p, prov = provider(item[1]), service(item[1])
    if prov == "self":
        return "self"
    if not p.issue or prov == "supabase-db":
        return "browser"
    if not p.admin:
        return "auto"
    if ctx is None:
        return "admin"
    return "auto" if admin_record(ctx, p.admin, item[0]) else "browser"


# ================================================================ reading current values


def read_target(ctx: Ctx, t: tpl.Template, names: list[str]) -> dict[str, str | None]:
    k = kind(t.kind)
    return k.read(ctx, t.address, names) if k.read else {}


def current(ctx: Ctx, item: Item) -> tuple[Record | None, dict[str, str]]:
    """The item's values: from the store, else recovered from wherever it is used."""
    rec = ctx.read(*item)
    if rec and rec.fields:
        return rec, rec.fields
    found: dict[str, str] = {}
    for t in sorted(ctx.users(item), key=lambda t: t.kind != "file"):
        names = t.vars_using(item)
        try:
            values = read_target(ctx, t, names)
        except RekeyError:
            continue
        for var in names:
            got = tpl.reverse(t.lines[var], values.get(var) or "")
            for (v, n, f), value in (got or {}).items():
                if (v, n) == item:
                    found.setdefault(f, value)
        if set(ctx.fields(item)) <= set(found):
            break
    return rec, found


# ================================================================ sync / deploy


def sync(ctx: Ctx, templates: list[tpl.Template], *, item: Item | None = None,
         values: dict[str, str] | None = None) -> tuple[list[tuple], list[str]]:
    """Write templates to their targets: every line, or only the lines that use `item`."""
    def lookup(v: str, n: str, f: str) -> str:
        return values[f] if values is not None and (v, n) == item else ctx.lookup(v, n, f)

    actions, failures = [], []
    for t in templates:
        names = t.vars_using(item) if item else list(t.lines)
        try:
            resolved = {var: tpl.resolve(t.lines[var], lookup) for var in names}
            secret = {var for var in names if tpl.REF.search(t.lines[var])}
            action = kind(t.kind).write(ctx, t.address, resolved, secret)
            if action:
                actions.append(action)
            ok(f"{t.rel}  {dim(', '.join(names))}")
        except (RekeyError, OSError) as e:     # one broken target must not stop the others
            fail(f"{t.rel}: {e}")
            failures.append(f"{t.rel}: {e}")
    return actions, failures


def resync_hint(rels: list[str]) -> str:
    return "rekey sync " + " ".join(f"targets/{r}.tpl" for r in dict.fromkeys(rels))


def offer_deploy(ctx: Ctx, actions: list[tuple]) -> tuple[list[str], bool]:
    """Redeploying restarts live services: each one only when the person says so (default: no).
    Returns the deploy failures and whether every service was redeployed."""
    actions = list(dict.fromkeys(actions))
    if not actions or ctx.dry_run:
        return [], True
    rel = lambda a: "/".join(a) + ("/production" if a[0] == "vercel" else "")
    say("\n" + _("The new values are set. Each service picks them up when it redeploys. One at a time (default: no):"))
    chosen = [a for a in actions if ctx.interactive and interactive() and ask("  " + _("Redeploy {name} now?", name=bold(rel(a))), default=False)]
    if later := [rel(a) for a in actions if a not in chosen]:
        say("    " + _("Deploy these later your usual way, or:") + " " + bold("rekey deploy " + " ".join(later)))
    return (deploy(ctx, chosen) if chosen else []), not later


def deploy(ctx: Ctx, actions: list[tuple], wait: int = 900) -> list[str]:
    actions = list(dict.fromkeys(actions))
    if not actions or ctx.dry_run:
        return []
    step(_("Redeploying: {n} — waiting until done (Ctrl-C: stop waiting)", n=len(actions)))
    checks, failures = {}, []
    for a in actions:
        name = "/".join(a)
        try:
            checks[name] = DEPLOY[a[0]](ctx, *a[1:])
        except RekeyError as e:
            fail(f"{name}: {e}")
            failures.append(_("{name}: redeploy failed", name=name))
    deadline, last = time.time() + wait, {}
    try:
        while checks and time.time() < deadline:
            for name, check in list(checks.items()):
                try:
                    state = check()
                except RekeyError:
                    state = "?"
                if state in HEALTHY:
                    ok(_("{name}: deploy healthy", name=name))
                    del checks[name]
                elif state == "NONE":
                    say(dim("    " + _("{name}: no production deployment, skipped", name=name)))
                    del checks[name]
                elif state in BROKEN:
                    fail(_("{name}: deploy failed ({state}) — check the logs", name=name, state=state))
                    failures.append(_("{name}: deploy failed", name=name))
                    del checks[name]
                elif last.get(name) != state:
                    say(dim(f"    {name}: {state}"))
                    last[name] = state
            if checks:
                time.sleep(10)
    except KeyboardInterrupt:
        say()
    failures += [_("{name}: deploy not confirmed", name=name) for name in checks]
    return failures


# ================================================================ rotate


def rotate(ctx: Ctx, items: list[Item], *, force: bool = False, redo: bool = False, apply_now: bool = True) -> int:
    """New key → 1Password → (apply_now) every place → offer redeploys → offer revoking.
    apply_now=False is `rekey issue`: only the new keys, places untouched until `rekey apply`."""
    from .setup import preflight

    if not ctx.dry_run and not preflight(ctx, items):
        return 1
    todo, skipped, waiting = [], [], []
    for item in items:
        m = ctx.meta(item)
        if not force and (m.get("locked") or "check" in m.get("tags", [])):
            skipped.append((item, m.get("locked") or m.get("note") or _("check before rotating")))
        elif not redo and (rec := ctx.read(*item)) and rec.state.get("revoke") is not None:   # never again before the old one is revoked
            waiting.append(item)
        else:
            todo.append(item)
    modes = {i: mode(i, ctx) for i in todo}
    # A DB password has no overlap: the old one dies when the new one is saved. Do those last, right before the redeploy.
    todo.sort(key=lambda i: (service(i[1]) == "supabase-db", modes[i] == "browser", i[1]))
    browser = [i for i in todo if modes[i] == "browser"]

    def report_waiting() -> None:
        if waiting:
            say(dim("  • " + _("Already rotated: {n} (revoke the old keys with: {cmd})", n=len(waiting), cmd="rekey revoke " + " ".join(i[1] for i in waiting))))
            if issued := [i[1] for i in waiting if ctx.read(*i).state.get("applied") is False]:
                say(dim("    " + _("Issued, not in place yet:") + " rekey apply " + " ".join(issued)))
            say(dim("    " + _("A new key came out wrong? Make it again: rekey rotate <key> --redo")))

    say()
    if not todo:
        say(bold(_("Nothing to rotate.")))
        for item, why in skipped:
            say(dim(f"  • {item[1]}: {why}  (" + _("to do it anyway: --force") + ")"))
        report_waiting()
        return 0
    if ctx.dry_run:
        say(dim(_("(dry-run: showing what would happen, changing nothing)")))
    say(bold(_("Keys to rotate: {n}. Each gets a new key, then every place that uses it is updated.", n=len(todo))))
    if len(todo) > len(browser):
        say("  • " + _("Automatic: {n} — just wait", n=len(todo) - len(browser)))
    if browser:
        say("  • " + _("In the browser: {n} — make the key on the page that opens and copy it:", n=len(browser)) + " "
            + ", ".join(f"{p}×{n}" if n > 1 else p for p, n in Counter(provider(i[1]).label for i in browser).items()))
    say("  • " + _("Places that change: {n}", n=len({t.rel for i in todo for t in ctx.users(i)})))
    report_waiting()
    for item, why in skipped:
        say(dim("  • " + _("skipped {key}: {why}", key=item[1], why=why)))
    if not apply_now:
        say(bold("  " + _("Only issuing: new keys go to {store}; no place changes until rekey apply.", store=ctx.store.label)))
    if not ctx.dry_run and ctx.interactive and interactive() and not ask("\n" + _("Start?")):
        return 0

    done, later, problems, actions, stopped = [], [], [], [], False
    try:
        for n, item in enumerate(todo, 1):
            if item is (browser[0] if browser else None) and len(browser) < len(todo):
                say(bold("\n" + _("Browser steps now: {n}.", n=len(browser))))
            step(f"[{n}/{len(todo)}] {item[1]}  {dim(provider(item[1]).label)}")
            try:
                a, f = rotate_one(ctx, item, modes[item], apply_now)
                actions += a
                problems += [f"{item[1]} → {x}" for x in f]
                done.append(item)
            except Skip as e:
                warn(str(e))
                later.append(item)
            except Stop:
                raise
            except RekeyError as e:
                fail(str(e))
                problems.append(f"{item[1]}: {e}")
    except Stop:
        stopped = True
        warn(_("Stopping here. Finished keys stay as they are."))
        later += [i for i in todo if i not in done and i not in later]
    failures, everywhere = offer_deploy(ctx, actions)
    problems += failures

    say()
    step(_("Result"))
    if not apply_now:
        ok(_("Issued: {n}. Nothing changed in the services yet.", n=len(done)))
        if later:
            warn(_("Left:") + " rekey issue " + " ".join(i[1] for i in later))
        for p in problems:
            fail(p)
        if done:
            say("  " + _("When you are ready to put them in place:") + " " + bold("rekey apply " + " ".join(i[1] for i in done)))
        return 1 if problems else 0
    ok(("(dry-run) " if ctx.dry_run else "") + _("Rotated: {n}", n=len(done)))
    if later:
        warn(_("Left:") + " rekey rotate " + " ".join(i[1] for i in later))
    for p in problems:
        fail(p)
    if failed := [p.split(" → ", 1)[1].split(": ", 1)[0] for p in problems if " → " in p]:
        say("  " + _("The new keys are saved. Fix the cause above, then write only the failed places again:"))
        say("  " + bold(resync_hint(failed)))
    if done and not ctx.dry_run:
        # rekey checks the variables, not what a running service has loaded: revoke only once all are redeployed.
        if everywhere and not problems and not stopped and ask("\n" + _("The rotated keys ({n}) are in place everywhere. Revoke the old keys now? (N to watch a little longer)", n=len(done)), default=False):
            return revoke(ctx, done)
        say(dim("  " + (_("When you are sure, revoke the old keys:") if everywhere else _("After the deploys, revoke the old keys:"))
                + " rekey revoke " + " ".join(i[1] for i in done)))
    return 1 if problems else 0


def rotate_one(ctx: Ctx, item: Item, how: str = "auto", apply_now: bool = True) -> tuple[list[tuple], list[str]]:
    rec, old = current(ctx, item)
    users = ctx.users(item)
    if ctx.dry_run:
        return sync(ctx, users, item=item, values={f: "dry-run" for f in ctx.fields(item)})
    ctx.vault = item[0]
    prov, m = provider(item[1]), ctx.meta(item)
    need = ctx.fields(item)
    if not apply_now and service(item[1]) == "supabase-db":
        # The old password stops the moment the new one is saved, so it can't wait for `rekey apply`.
        raise Skip(_("a database password can't be issued ahead: do it with rekey rotate {key} when you are ready", key=item[1]))
    if how == "self" and any(re.match(r"[A-Za-z]{2,10}_", v) for v in old.values()):
        # rk_…, sk_…: a service issued it, so a random value would be rejected wherever it is checked.
        raise Skip(_("the old value looks issued by a service ({prefix}…), not made up: rename the key after its service", prefix=next(iter(old.values())).split("_")[0] + "_"))
    new, meta = None, {}
    if prov.issue and not (how == "browser" and prov.admin):     # no admin key: skip the API, go to the browser
        try:
            new, meta = prov.issue(ctx, item[1], old or {f: "" for f in need})
            if how != "browser":
                ok(_("new value generated") if how == "self" else _("new key issued"))
        except RekeyError as e:      # no admin key, no permission, API down: the browser always works
            say(dim("    " + _("can't do it automatically ({why}) → browser", why=str(e).splitlines()[0][:100])))
    by_hand = new is None
    if by_hand:
        say(dim("    " + _("used in:") + " " + ", ".join(t.rel for t in users)))
        page = m.get("page", "")
        if not page and prov.locate:
            try:
                page = prov.locate(ctx, item, old)
            except RekeyError:
                pass
        new = from_browser(ctx, item[1], prov, old, need, m.get("note", ""), page)
    while (good := works(prov, new)) is False:
        warn(_("The new key doesn't work. It may be the wrong copy, or it lacks permissions."))
        if not by_hand:
            if ask("    " + _("Continue anyway?"), default=False):
                break
            raise RekeyError(_("Stopped: the new key doesn't work (nothing was changed)"))
        ans = input("    " + _("Enter: copy again · y: continue anyway · s: skip") + " › ").strip().lower()
        if ans == "y":
            break
        if ans == "s":
            raise Skip(_("skipped"))
        new = from_browser(ctx, item[1], prov, old, need, again=new)
    if missing := set(need) - set(new):
        raise RekeyError(_("The new value lacks {fields}", fields=sorted(missing)))
    if good:
        ok(_("the new key works"))
    if rec and rec.state.get("revoke") is not None:     # --redo: the key that still has to be revoked stays the old one
        previous, revoke = rec.previous, rec.state["revoke"]
    else:
        previous, revoke = old, ((rec.state.get("meta", {}) if rec else {}) if old else None)
    new_rec = Record(new, previous=previous, state={"meta": meta, "revoke": revoke, "applied": apply_now})
    new_rec.stamp()
    ctx.write(*item, new_rec)
    ok(_("saved to {store} (the old value is kept until it is revoked)", store=ctx.store.label))
    return sync(ctx, users, item=item, values=new) if apply_now else ([], [])


def apply(ctx: Ctx, items: list[Item]) -> int:
    """Put issued keys (rekey issue) in place everywhere, then offer the redeploys."""
    todo = [(i, r) for i in items if (r := ctx.read(*i)) and r.state.get("applied") is False]
    if not todo:
        say(dim(_("Nothing to apply: no issued keys waiting (rekey issue makes them).")))
        return 0
    say(bold(_("Keys to put in place: {n}", n=len(todo))))
    actions, problems = [], []
    for item, rec in todo:
        step(item[1])
        a, f = sync(ctx, ctx.users(item), item=item, values=rec.fields)
        actions += a
        problems += [f"{item[1]} → {x}" for x in f]
        if not f:
            rec.state["applied"] = True
            ctx.write(*item, rec)
    problems += offer_deploy(ctx, actions)[0]
    for p in problems:
        fail(p)
    say(dim("  " + _("After the deploys, revoke the old keys:") + " rekey revoke " + " ".join(i[1] for i, _r in todo)))
    return 1 if problems else 0


# ================================================================ revoke


def still_used(ctx: Ctx, item: Item, old: dict[str, str]) -> tuple[list[str], list[str]]:
    """Places that still hold the old value (revoking would break them), and places that can't be read.

    Every place with a key of the same service is checked, not only this key's: a key that was split
    (arrange) or copied by hand still holds the same old value under another name."""
    svc, olds = service(item[1]), [v.strip() for v in old.values() if len(v.strip()) >= 8]
    hits, unknown = [], []
    for t in ctx.templates:
        names = [var for var, raw in t.lines.items() if any(service(n) == svc for _v, n, _f in tpl.REF.findall(raw))]
        if not names:
            continue
        if not kind(t.kind).read:
            unknown.append(t.rel)
            continue
        try:
            values = ctx.cached("read:" + t.rel, lambda t=t: read_target(ctx, t, list(t.lines)))
        except RekeyError:
            unknown.append(t.rel)
            continue
        for var in names:
            value = values.get(var)
            if value is None:
                unknown.append(f"{t.rel} {var}")
            elif any(o in value for o in olds):
                hits.append(f"{t.rel} {var}")
    return hits, unknown


def revoke_one(ctx: Ctx, item: Item, rec: Record) -> str:
    """By API when possible; MANUAL + text when the person has to delete it."""
    if service(item[1]) in ("self", "supabase-db"):
        return _("the old value is no longer used anywhere")
    prov = provider(item[1])
    if prov.revoke:
        try:
            return prov.revoke(ctx, item[1], rec.previous, rec.state.get("revoke") or {})
        except Unavailable:
            pass
    return MANUAL + _("Delete the old key.")


def revoke(ctx: Ctx, items: list[Item], *, force: bool = False) -> int:
    pending = [(i, r) for i in items if (r := ctx.read(*i)) and r.state.get("revoke") is not None]
    if unapplied := [i[1] for i, r in pending if r.state.get("applied") is False]:
        warn(_("Issued but not in place yet, so the old key is still in use:") + " rekey apply " + " ".join(unapplied))
        pending = [(i, r) for i, r in pending if r.state.get("applied") is not False]
    if not pending:
        say(dim(_("No old keys to revoke.")))
        return 0
    pending.sort(key=lambda p: (provider(p[0][1]).revoke is None, p[0][1]))
    say(bold(_("Old keys to revoke: {n}", n=len(pending))))
    left = []
    for n, (item, rec) in enumerate(pending, 1):
        prov = provider(item[1])
        step(f"[{n}/{len(pending)}] {item[1]}  {dim(prov.label)}")
        hits, unknown = still_used(ctx, item, rec.previous)
        if hits and not force:
            fail(_("Stopping: the old value is still used in") + " " + ", ".join(hits))
            say("    " + _("Rotate the keys there (or write the new value), then revoke again:") + " " + bold(resync_hint([h.split(" ")[0] for h in hits])))
            left.append(item[1])
            continue
        if unknown and not force:
            warn(_("These places can't be read, so rekey can't tell whether they still use the old key:") + " " + ", ".join(unknown))
            if not ask("    " + _("Revoking breaks them if they do. Revoke anyway?"), default=False):
                left.append(item[1])
                continue
        if ctx.dry_run:
            continue
        ctx.vault = item[0]
        try:
            msg = revoke_one(ctx, item, rec)
            if msg.startswith(MANUAL):
                v = rec.previous.get("credential", "")
                tail = "  " + bold(_("ends in …{tail}", tail=v[-4:])) if len(v) > 12 and "\n" not in v else ""
                if rec.state.get("undo"):                     # going back: the key to delete is the rekey_… one
                    say("    " + _("Delete the new key {name}… (the old one stays)", name=key_name(item[1], "x")[:-1]) + tail)
                else:
                    say(f"    {msg[len(MANUAL):]}" + tail + dim("  (" + _("keep {name}…, that is the new one", name=key_name(item[1], "x")[:-1]) + ")"))
                open_url(ctx.meta(item).get("page") or prov.page)
                if not ask("    " + _("Deleted it?")):
                    left.append(item[1])
                    continue
                msg = _("deletion confirmed")
            ok(msg)
        except RekeyError as e:
            fail(str(e))
            left.append(item[1])
            continue
        rec.previous, rec.state["revoke"] = {}, None
        rec.state.pop("undo", None)
        ctx.write(*item, rec)
    if left:
        warn(_("Left:") + " rekey revoke " + " ".join(left))
    return 1 if left else 0


def undo(ctx: Ctx, items: list[Item]) -> int:
    """Before the old key is revoked: put it back everywhere, then delete the new one."""
    pending = [(i, r) for i in items if (r := ctx.read(*i)) and r.state.get("revoke") is not None and r.previous]
    if not pending:
        say(dim(_("Nothing to undo: only keys rotated and not yet revoked can go back.")))
        return 0
    say(bold(_("Back to the old key: {n}", n=len(pending))))
    actions, failed, done = [], [], []
    for item, rec in pending:
        step(item[1])
        a, f = sync(ctx, ctx.users(item), item=item, values=rec.previous)
        actions += a
        if f:
            failed.append(item[1])
            continue
        # The new key is now the one to delete: if this stops here, `rekey revoke` finishes the job.
        ctx.write(*item, Record(rec.previous, previous=rec.fields,
                                state={"meta": rec.state["revoke"], "revoke": rec.state.get("meta") or {}, "undo": True}))
        done.append(item)
    failures, everywhere = offer_deploy(ctx, actions)
    failed += failures
    if not everywhere:                           # some services still run the new key: deleting it now would break them
        say("    " + _("After the deploy, delete the new keys:") + " " + bold("rekey revoke " + " ".join(i[1] for i in done)))
    elif not failed and done:
        revoke(ctx, [i for i in done])
    if failed:
        warn(_("Left:") + " " + ", ".join(failed))
    return 1 if failed else 0


# ================================================================ import / diff


def import_(ctx: Ctx, items: list[Item]) -> int:
    """Put values that are only in .env files and platforms into the store, without rotating."""
    missing = saved = 0
    for item in items:
        rec, found = current(ctx, item)
        if rec and rec.fields:
            continue
        if not set(ctx.fields(item)) <= set(found):
            warn(_("{key}: current value not found", key=item[1]))
            missing += 1
            continue
        if not ctx.dry_run:
            r = Record(found)
            r.stamp()
            ctx.write(*item, r)
        ok(item[1])
        saved += 1
    say(_("Saved to {store}: {n}", n=saved, store=ctx.store.label) + (", " + _("not found: {n}", n=missing) if missing else "")
        + (" " + _("(keys already stored were left alone)") if saved < len(items) - missing else ""))
    return 1 if missing else 0


def diff(ctx: Ctx, templates: list[tpl.Template]) -> int:
    """Compare what the templates say with what the targets hold. Secret values are not shown."""
    changed, differ = 0, []
    for t in templates:
        if not kind(t.kind).read:
            say(dim(f"  {t.rel}: " + _("values of this kind can't be read")))
            continue
        have = read_target(ctx, t, list(t.lines))
        for var, raw in t.lines.items():
            secret = bool(tpl.REF.search(raw))
            try:
                want = tpl.resolve(raw, ctx.lookup)
            except RekeyError as e:
                warn(f"{t.rel} {var}: {e}")
                continue
            got = have.get(var, "<" + _("missing") + ">")
            if got is None or got.strip() == want.strip():
                continue
            changed += 1
            differ.append(t.rel)
            say(f"  ~ {t.rel} {var}" + ("" if secret else f": {got!r} → {want!r}"))
    if changed:
        warn(_("Differences: {n}. To match the templates:", n=changed) + " " + resync_hint(differ))
    else:
        ok(_("no differences"))
    return 1 if changed else 0
