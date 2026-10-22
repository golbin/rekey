"""The operations. Everything is derived from two plain-text sources:

    targets/**.tpl   where each key is used (and plain settings)   — git
    keys.toml        exceptions only: tags, notes, locked, page    — git
and the values in 1Password.
"""

from __future__ import annotations

import fnmatch
import os
import time
import tomllib
from collections import Counter
from typing import Any, Callable

from . import tpl
from .providers import MANUAL, Skip, Stop, Unavailable, from_browser, provider, works
from .store import Record
from .targets import BROKEN, DEPLOY, HEALTHY, kind
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
        return self.cached(f"rec:{vault}/{name}", lambda: self.store.read(vault, name))

    def write(self, vault: str, name: str, rec: Record) -> None:
        self.store.write(vault, name, rec, self.meta(name).get("tags", []))
        self._cache[f"rec:{vault}/{name}"] = rec

    def lookup(self, vault: str, name: str, field: str) -> str:
        rec = self.read(vault, name)
        if not rec or field not in rec.fields:
            raise RekeyError(f"{name} 값이 {self.store.label} '{vault}'에 없습니다. vault 권한을 확인하세요 (처음 도입 중이면 rekey import {name})")
        return rec.fields[field]

    # -- structure
    def items(self) -> list[Item]:
        return sorted({i for t in self.templates for i in t.items()}, key=lambda i: i[1])

    def users(self, item: Item) -> list[tpl.Template]:
        return [t for t in self.templates if item in t.items()]

    def fields(self, item: Item) -> list[str]:
        return sorted({f for t in self.users(item) for raw in t.lines.values()
                       for v, n, f in tpl.REF.findall(raw) if (v, n) == item})

    def meta(self, name: str) -> dict[str, Any]:
        return self.keys.get(name, {})

    def select(self, selectors: list[str]) -> list[Item]:
        """name or glob · tag:<tag> · in:<template glob> · all. Items tagged 'retire' only by name."""
        out = []
        for item in self.items():
            name, m = item[1], self.meta(item[1])
            for sel in selectors:
                kind_, _, arg = sel.partition(":")
                hit = (sel == "all" and "retire" not in m.get("tags", [])) \
                    or (kind_ == "tag" and arg in m.get("tags", [])) \
                    or (kind_ == "in" and any(fnmatch.fnmatch(t.rel, arg) for t in self.users(item))) \
                    or fnmatch.fnmatch(name, sel)
                if hit:
                    out.append(item)
                    break
        if not out:
            raise RekeyError(f"{' '.join(selectors)}에 해당하는 키가 없습니다 (rekey ls)")
        return out

    def template(self, rel: str) -> tpl.Template:
        rel = rel.removeprefix("targets/").removesuffix(".tpl")
        for t in self.templates:
            if t.rel == rel:
                return t
        raise RekeyError(f"템플릿이 없습니다: targets/{rel}.tpl")


def mode(item: Item, ctx: Ctx | None = None) -> str:
    """self · auto · admin (auto when the admin key exists) · browser. With ctx, 'admin' is resolved."""
    p, prov = provider(item[1]), item[1].split(".")[0]
    if prov == "self":
        return "self"
    if not p.issue or prov == "supabase-db":
        return "browser"
    if not p.admin:
        return "auto"
    if ctx is None:
        return "admin"
    rec = ctx.read(item[0], f"rekey.{p.admin}")
    return "auto" if rec and rec.fields else "browser"


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
            ctx.secret_vars = {var for var in names if tpl.REF.search(t.lines[var])}
            action = kind(t.kind).write(ctx, t.address, resolved)
            if action:
                actions.append(action)
            ok(f"{t.rel}  {dim(', '.join(names))}")
        except (RekeyError, OSError) as e:     # one broken target must not stop the others
            fail(f"{t.rel}: {e}")
            failures.append(f"{t.rel}: {e}")
    return actions, failures


def resync_hint(rels: list[str]) -> str:
    return "rekey sync " + " ".join(f"targets/{r}.tpl" for r in dict.fromkeys(rels))


def deploy(ctx: Ctx, actions: list[tuple], wait: int = 900) -> list[str]:
    actions = list(dict.fromkeys(actions))
    if not actions or ctx.dry_run:
        return []
    step(f"재배포 {len(actions)}곳 — 끝날 때까지 확인합니다 (Ctrl-C: 그만 기다리기)")
    checks, failures = {}, []
    for a in actions:
        name = "/".join(a)
        try:
            checks[name] = DEPLOY[a[0]](ctx, *a[1:])
        except RekeyError as e:
            fail(f"{name}: {e}")
            failures.append(f"{name} 재배포 실패")
    deadline, last = time.time() + wait, {}
    try:
        while checks and time.time() < deadline:
            for name, check in list(checks.items()):
                try:
                    state = check()
                except RekeyError:
                    state = "?"
                if state in HEALTHY:
                    ok(f"{name} 배포 정상")
                    del checks[name]
                elif state == "NONE":
                    say(dim(f"    {name}: 프로덕션 배포가 없어 건너뜀"))
                    del checks[name]
                elif state in BROKEN:
                    fail(f"{name} 배포 실패 ({state}) — 로그를 확인하세요")
                    failures.append(f"{name} 배포 실패")
                    del checks[name]
                elif last.get(name) != state:
                    say(dim(f"    {name}: {state}"))
                    last[name] = state
            if checks:
                time.sleep(10)
    except KeyboardInterrupt:
        say()
    failures += [f"{name} 배포 확인 못함" for name in checks]
    return failures


# ================================================================ rotate


def rotate(ctx: Ctx, items: list[Item], *, force: bool = False) -> int:
    from .setup import preflight

    if not ctx.dry_run and not preflight(ctx, items):
        return 1
    todo, skipped, waiting = [], [], []
    for item in items:
        m = ctx.meta(item[1])
        if not force and (m.get("locked") or "check" in m.get("tags", [])):
            skipped.append((item, m.get("locked") or m.get("note") or "교체 전 확인 필요"))
        elif (rec := ctx.read(*item)) and rec.state.get("revoke") is not None:   # never again before the old one is revoked
            waiting.append(item)
        else:
            todo.append(item)
    modes = {i: mode(i, ctx) for i in todo}
    todo.sort(key=lambda i: (modes[i] == "browser", i[1]))
    browser = [i for i in todo if modes[i] == "browser"]

    say()
    if not todo:
        say(bold("교체할 키가 없습니다."))
        for item, why in skipped:
            say(dim(f"  • {item[1]}: {why}  (그래도 하려면 --force)"))
        if waiting:
            say(dim("  • 이미 교체됨, 옛 키 폐기 대기: rekey revoke " + " ".join(i[1] for i in waiting)))
        return 0
    if ctx.dry_run:
        say(dim("(dry-run: 아무것도 바꾸지 않고 보여 주기만 합니다)"))
    say(bold(f"키 {len(todo)}개를 새로 발급해 모든 사용처를 바꿉니다."))
    if len(todo) > len(browser):
        say(f"  • 자동 {len(todo) - len(browser)}개 — 기다리기만 하면 됩니다")
    if browser:
        say(f"  • 브라우저 {len(browser)}개 — 열린 페이지에서 키를 만들고 복사만: "
            + ", ".join(f"{p}×{n}" if n > 1 else p for p, n in Counter(provider(i[1]).label for i in browser).items()))
    say(f"  • 바뀌는 곳 {len({t.rel for i in todo for t in ctx.users(i)})}곳")
    if waiting:
        say(dim(f"  • 이미 교체됨 {len(waiting)}개 (옛 키 폐기 대기: rekey revoke " + " ".join(i[1] for i in waiting) + ")"))
    for item, why in skipped:
        say(dim(f"  • 건너뜀 {item[1]}: {why}"))
    if not ctx.dry_run and ctx.interactive and interactive() and not ask("\n시작할까요?"):
        return 0

    done, later, problems, actions, stopped = [], [], [], [], False
    try:
        for n, item in enumerate(todo, 1):
            if item is (browser[0] if browser else None) and len(browser) < len(todo):
                say(bold(f"\n이제 브라우저 단계 {len(browser)}개입니다."))
            step(f"[{n}/{len(todo)}] {item[1]}  {dim(provider(item[1]).label)}")
            try:
                a, f = rotate_one(ctx, item, modes[item])
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
        warn("여기서 멈춥니다. 끝난 키는 그대로입니다.")
        later += [i for i in todo if i not in done and i not in later]
    problems += deploy(ctx, actions)

    say()
    step("결과")
    ok(f"{'(dry-run) ' if ctx.dry_run else ''}교체 {len(done)}개")
    if later:
        warn("남은 키: rekey rotate " + " ".join(i[1] for i in later))
    for p in problems:
        fail(p)
    if failed := [p.split(" → ", 1)[1].split(": ", 1)[0] for p in problems if " → " in p]:
        say("  새 키는 저장됐습니다. 위 원인을 해결한 뒤 실패한 곳만 다시 반영하세요:")
        say("  " + bold(resync_hint(failed)))
    if done and not ctx.dry_run:
        if not problems and not stopped and ask(f"\n교체한 {len(done)}개는 모든 곳에 반영됐습니다. 옛 키를 지금 폐기할까요? (더 지켜보려면 N)", default=False):
            return revoke(ctx, done)
        say(dim("  확인 후 옛 키 폐기: rekey revoke " + " ".join(i[1] for i in done)))
    return 1 if problems else 0


def rotate_one(ctx: Ctx, item: Item, how: str = "auto") -> tuple[list[tuple], list[str]]:
    rec, old = current(ctx, item)
    users = ctx.users(item)
    if ctx.dry_run:
        return sync(ctx, users, item=item, values={f: "dry-run" for f in ctx.fields(item)})
    ctx.vault = item[0]
    prov, m = provider(item[1]), ctx.meta(item[1])
    need = ctx.fields(item)
    new, meta = None, {}
    if prov.issue and not (how == "browser" and prov.admin):     # no admin key: skip the API, go to the browser
        try:
            new, meta = prov.issue(ctx, item[1], old or {f: "" for f in need})
            if how != "browser":
                ok("새 값 생성" if how == "self" else "새 키 발급")
        except RekeyError as e:      # no admin key, no permission, API down: the browser always works
            say(dim(f"    자동으로 못 함 ({str(e).splitlines()[0][:100]}) → 브라우저로"))
    by_hand = new is None
    if by_hand:
        say(dim("    쓰는 곳: " + ", ".join(t.rel for t in users)))
        new = from_browser(ctx, item[1], prov, old, need, m.get("note", ""), m.get("page", ""))
    while (good := works(prov, new)) is False:
        warn("새 키가 동작하지 않습니다. 복사가 잘못됐거나 권한이 부족할 수 있습니다.")
        if not by_hand:
            if ask("    그래도 진행할까요?", default=False):
                break
            raise RekeyError("새 키가 동작하지 않아 중단 (아무 곳도 바뀌지 않음)")
        ans = input("    다시 복사하려면 Enter · 그대로 진행 y · 건너뛰기 s › ").strip().lower()
        if ans == "y":
            break
        if ans == "s":
            raise Skip("건너뜀")
        new = from_browser(ctx, item[1], prov, old, need, again=new)
    if missing := set(need) - set(new):
        raise RekeyError(f"새 값에 {sorted(missing)}이(가) 없습니다")
    if good:
        ok("새 키로 API 호출 성공")
    new_rec = Record(new, previous=old, state={"meta": meta, "revoke": (rec.state.get("meta", {}) if rec else {}) if old else None})
    new_rec.stamp()
    ctx.write(*item, new_rec)
    ok(f"{ctx.store.label}에 저장 (옛 값은 폐기 때까지 보관)")
    return sync(ctx, users, item=item, values=new)


# ================================================================ revoke


def still_used(ctx: Ctx, item: Item, old: dict[str, str]) -> list[str]:
    """Readable targets that still hold the old value: revoking now would break them."""
    hits = []
    for t in ctx.users(item):
        names = t.vars_using(item)
        try:
            values = read_target(ctx, t, names)
        except RekeyError:
            continue
        for var in names:
            try:
                was = tpl.resolve(t.lines[var], lambda v, n, f: old[f] if (v, n) == item else ctx.lookup(v, n, f))
            except (KeyError, RekeyError):
                continue
            if (values.get(var) or "").strip() == was.strip():
                hits.append(f"{t.rel} {var}")
    return hits


def revoke_one(ctx: Ctx, item: Item, rec: Record) -> str:
    """By API when possible; MANUAL + text when the person has to delete it."""
    if item[1].startswith(("self.", "supabase-db.")):
        return "옛 값은 이미 쓰이지 않습니다"
    prov = provider(item[1])
    if prov.revoke:
        try:
            return prov.revoke(ctx, item[1], rec.previous, rec.state.get("revoke") or {})
        except Unavailable:
            pass
    return MANUAL + "옛 키를 삭제하세요."


def revoke(ctx: Ctx, items: list[Item], *, force: bool = False) -> int:
    pending = [(i, r) for i in items if (r := ctx.read(*i)) and r.state.get("revoke") is not None]
    if not pending:
        say(dim("폐기할 옛 키가 없습니다."))
        return 0
    pending.sort(key=lambda p: (provider(p[0][1]).revoke is None, p[0][1]))
    say(bold(f"옛 키 {len(pending)}개 폐기"))
    left = []
    for n, (item, rec) in enumerate(pending, 1):
        prov = provider(item[1])
        step(f"[{n}/{len(pending)}] {item[1]}  {dim(prov.label)}")
        if (hits := still_used(ctx, item, rec.previous)) and not force:
            fail("아직 옛 값을 쓰는 곳이 있어 멈춥니다: " + ", ".join(hits))
            say("    새 값으로 바꾼 뒤 다시 폐기하세요: " + bold(resync_hint([h.split(" ")[0] for h in hits])))
            left.append(item[1])
            continue
        if ctx.dry_run:
            continue
        ctx.vault = item[0]
        try:
            msg = revoke_one(ctx, item, rec)
            if msg.startswith(MANUAL):
                v = rec.previous.get("credential", "")
                say(f"    {msg[len(MANUAL):]}" + (f"  {bold('끝자리 …' + v[-4:])}" if len(v) > 12 and "\n" not in v else "")
                    + dim(f"  (rekey-{item[1]}-… 은 새 키이니 두세요)"))
                open_url(ctx.meta(item[1]).get("page") or prov.page)
                if not ask("    지웠나요?"):
                    left.append(item[1])
                    continue
                msg = "삭제 확인"
            ok(msg)
        except RekeyError as e:
            fail(str(e))
            left.append(item[1])
            continue
        rec.previous, rec.state["revoke"] = {}, None
        ctx.write(*item, rec)
    if left:
        warn("남은 키: rekey revoke " + " ".join(left))
    return 1 if left else 0


# ================================================================ import / diff


def import_(ctx: Ctx, items: list[Item]) -> int:
    """Put values that are only in .env files and platforms into the store, without rotating."""
    missing = saved = 0
    for item in items:
        rec, found = current(ctx, item)
        if rec and rec.fields:
            continue
        if not set(ctx.fields(item)) <= set(found):
            warn(f"{item[1]}: 현재 값을 찾지 못했습니다")
            missing += 1
            continue
        if not ctx.dry_run:
            r = Record(found)
            r.stamp()
            ctx.write(*item, r)
        ok(item[1])
        saved += 1
    say(f"{ctx.store.label}에 {saved}개 저장" + (f", {missing}개는 값을 찾지 못함" if missing else "") + (" (이미 있던 키는 그대로)" if saved < len(items) - missing else ""))
    return 1 if missing else 0


def diff(ctx: Ctx, templates: list[tpl.Template]) -> int:
    """Compare what the templates say with what the targets hold. Secret values are not shown."""
    changed, differ = 0, []
    for t in templates:
        if not kind(t.kind).read:
            say(dim(f"  {t.rel}: 값을 읽을 수 없는 종류"))
            continue
        have = read_target(ctx, t, list(t.lines))
        for var, raw in t.lines.items():
            secret = bool(tpl.REF.search(raw))
            try:
                want = tpl.resolve(raw, ctx.lookup)
            except RekeyError as e:
                warn(f"{t.rel} {var}: {e}")
                continue
            got = have.get(var, "<없음>")
            if got is None or got.strip() == want.strip():
                continue
            changed += 1
            differ.append(t.rel)
            say(f"  ~ {t.rel} {var}" + ("" if secret else f": {got!r} → {want!r}"))
    if changed:
        warn(f"차이 {changed}개. 템플릿대로 맞추려면: {resync_hint(differ)}")
    else:
        ok("차이 없음")
    return 1 if changed else 0
