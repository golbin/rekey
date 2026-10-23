"""python3 -m unittest discover -s tests"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["REKEY_LANG"] = "en"       # the assertions below read English messages

from rekey_lib import core, tpl  # noqa: E402
from rekey_lib.init import init  # noqa: E402
from rekey_lib.store import FileStore  # noqa: E402
from rekey_lib.targets import parse_dotenv, write_file  # noqa: E402

V = "Test Vault"
OPENAI = "sk-proj-" + "a" * 40
SB_URL = "postgresql://postgres.abcref:oldpw@aws-0.pooler.supabase.com:5432/postgres"


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class Templates(unittest.TestCase):
    def test_resolve_and_reverse(self):
        raw = "postgresql://u:" + tpl.ref(V, "web.supabase-db", "password") + "@host/db"
        self.assertEqual(tpl.resolve(raw, lambda v, n, f: "p@ss"), "postgresql://u:p@ss@host/db")
        self.assertEqual(tpl.reverse(raw, "postgresql://u:secret@host/db"), {(V, "web.supabase-db", "password"): "secret"})
        self.assertIsNone(tpl.reverse(raw, "mysql://x"))
        t = tpl.parse("# c\nA=1\nB=" + tpl.ref(V, "x.y") + "\n", "file/a/.env")
        self.assertEqual(t.items(), {(V, "x.y")})
        self.assertEqual(t.vars_using((V, "x.y")), ["B"])
        self.assertEqual((t.kind, t.address), ("file", ["a", ".env"]))


class Dotenv(unittest.TestCase):
    def test_write_keeps_everything_else(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, ".env")
        write(p, "# c\nexport A=old\nQ='x y'\nM='{\n  \"k\": 1\n}'\nKEEP=1 # note\n")
        ctx = type("C", (), {"root": d, "dry_run": False})()
        write_file(ctx, [".env"], {"A": "new", "M": '{\n "k": 2\n}', "NEW": "v w"})
        self.assertIn("# c\nexport A=new\n", read(p))
        self.assertIn("KEEP=1 # note\n", read(p))
        self.assertEqual(parse_dotenv(read(p)), {"A": "new", "Q": "x y", "M": '{\n "k": 2\n}', "KEEP": "1", "NEW": "v w"})


class Flow(unittest.TestCase):
    """init → import → rotate → revoke → sync → diff on a fake workspace with locally generated keys."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.home = os.path.join(self.root, "rekey")
        os.makedirs(self.home)
        write(f"{self.root}/web/.env.local",
              f"OPENAI_API_KEY={OPENAI}\nAUTH_SECRET=old-auth-secret-1\nDATABASE_URL={SB_URL}\nAPP_URL=http://localhost\n"
              "R2_ACCESS_KEY_ID=ak123456789\nR2_SECRET_ACCESS_KEY=sk123456789\nDATA_MASTER_KEY=do-not-touch-12\n")
        write(f"{self.root}/api/.env", f"OPENAI_API_KEY={OPENAI}\nRUNNER_AUTH_SECRET=old-auth-secret-1\n")
        self.store = FileStore(os.path.join(self.root, "store.json"))
        os.environ["REKEY_ROOT"] = self.root
        self.out = io.StringIO()

    def ctx(self, **kw):
        return core.Ctx(self.home, self.store, interactive=False, **kw)

    def run_(self, fn, *a, **kw):
        with redirect_stdout(self.out):
            return fn(*a, **kw)

    def test_full_cycle(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={"web": ["file/web/"]}, retire=[])
        ctx = self.ctx()
        names = [n for _, n in ctx.items()]
        self.assertIn("api.openai", names)                       # one item for the key copied twice
        self.assertEqual(len(ctx.users((V, "api.openai"))), 2)
        self.assertIn("web.supabase-db", names)               # password inside a URL
        self.assertIn("web.cloudflare", names)                # R2 pair
        self.assertNotIn("APP_URL", ctx.template("file/web/.env.local").lines)   # local settings stay local
        self.assertIn("locked", ctx.meta("web.self.data-master-key"))
        self.assertIn("web", ctx.meta("api.openai")["tags"])
        self.assertNotIn(OPENAI, read(f"{self.home}/targets/web/file/web/.env.local.tpl"))

        self.assertEqual(self.run_(core.import_, self.ctx(), self.ctx().select(["all"])), 0)
        self.assertEqual(self.store.read(V, "web.supabase-db").fields, {"password": "oldpw"})

        secret = [i for i in self.ctx().items() if i[1] == "api.self.auth-secret"][0]
        self.assertEqual(self.run_(core.rotate, self.ctx(), [secret]), 0)
        web, api = parse_dotenv(read(f"{self.root}/web/.env.local")), parse_dotenv(read(f"{self.root}/api/.env"))
        self.assertNotEqual(web["AUTH_SECRET"], "old-auth-secret-1")
        self.assertEqual(web["AUTH_SECRET"], api["RUNNER_AUTH_SECRET"])          # same key, both places
        self.assertEqual(web["DATABASE_URL"], SB_URL)                            # untouched
        rec = self.store.read(*secret)
        self.assertEqual(rec.previous, {"credential": "old-auth-secret-1"})

        before = web["AUTH_SECRET"]
        self.run_(core.rotate, self.ctx(), [secret])                             # waits for revoke → skipped
        self.assertEqual(parse_dotenv(read(f"{self.root}/web/.env.local"))["AUTH_SECRET"], before)

        self.assertEqual(self.run_(core.revoke, self.ctx(), [secret]), 0)
        self.assertEqual(self.store.read(*secret).previous, {})

        os.remove(f"{self.root}/api/.env")                                        # a new machine
        self.run_(core.sync, self.ctx(), [self.ctx().template("file/api/.env")])
        self.assertEqual(parse_dotenv(read(f"{self.root}/api/.env"))["OPENAI_API_KEY"], OPENAI)

        write(f"{self.root}/api/.env", "OPENAI_API_KEY=drifted\n")
        self.assertEqual(self.run_(core.diff, self.ctx(), [self.ctx().template("file/api/.env")]), 1)

        for v in (OPENAI, "oldpw", "old-auth-secret-1", before):
            self.assertNotIn(v, self.out.getvalue())

    def test_locked_browser_and_dry_run(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        self.run_(core.import_, self.ctx(), self.ctx().select(["all"]))
        before = read(f"{self.root}/web/.env.local")
        self.run_(core.rotate, self.ctx(dry_run=True), self.ctx().select(["all"]))
        self.assertEqual(read(f"{self.root}/web/.env.local"), before)
        self.assertEqual(self.run_(core.rotate, self.ctx(), self.ctx().select(["*.openai", "web.self.data-*"])), 0)
        self.assertEqual(read(f"{self.root}/web/.env.local"), before)        # browser needed, locked skipped
        self.assertIn("Left: rekey rotate api.openai", self.out.getvalue())
        self.assertIn("skipped web.self.data-master-key", self.out.getvalue())

    def test_revoke_refuses_while_old_value_is_used(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = [i for i in self.ctx().items() if i[1] == "api.self.auth-secret"][0]
        self.run_(core.rotate, self.ctx(), [secret])
        write(f"{self.root}/api/.env", "RUNNER_AUTH_SECRET=old-auth-secret-1\n")
        self.assertEqual(self.run_(core.revoke, self.ctx(), [secret]), 1)


    def test_one_broken_target_does_not_stop_the_others(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = (V, "api.self.auth-secret")
        os.chmod(f"{self.root}/api", 0o555)
        try:
            self.assertEqual(self.run_(core.rotate, self.ctx(), [secret]), 1)
        finally:
            os.chmod(f"{self.root}/api", 0o755)
        self.assertNotEqual(parse_dotenv(read(f"{self.root}/web/.env.local"))["AUTH_SECRET"], "old-auth-secret-1")
        self.assertIn("rekey sync targets/api/file/api/.env.tpl", self.out.getvalue())

    def test_pending_key_is_not_rotated_again_even_with_force(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = (V, "api.self.auth-secret")
        self.run_(core.rotate, self.ctx(), [secret])
        first = self.store.read(*secret)
        self.run_(core.rotate, self.ctx(), [secret], force=True)
        self.assertEqual(self.store.read(*secret).previous, first.previous)      # the real old key stays on record
        self.assertIn("Already rotated: 1", self.out.getvalue())
        self.run_(core.rotate, self.ctx(), [secret], redo=True)              # the new one was wrong: make it again
        again = self.store.read(*secret)
        self.assertNotEqual(again.fields, first.fields)
        self.assertEqual(again.previous, first.previous)
        self.run_(core.undo, self.ctx(), [secret])                         # changed my mind: the old one back
        back = self.store.read(*secret)
        self.assertEqual(back.fields, first.previous)
        self.assertFalse(back.previous)


    def test_one_key_per_project(self):
        from rekey_lib.arrange import arrange
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        self.run_(arrange, self.ctx(), "Test - {env}")
        ctx = self.ctx()
        projects = {i[1]: {ctx.project(t) for t in ctx.users(i)} for i in ctx.items()}
        self.assertEqual(projects["api.self.auth-secret"], {"api", "web"})      # our services share their own tokens
        self.assertEqual(projects["web.openai"], {"web"})                        # a copied key: one per project
        self.assertEqual(projects["api.openai"], {"api"})
        self.assertEqual(ctx.select(["project:api"]), [i for i in ctx.items() if "api" in projects[i[1]]])

    def test_issue_then_apply(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = (V, "api.self.auth-secret")
        before = open(f"{self.root}/api/.env").read()
        self.run_(core.rotate, self.ctx(), [secret], apply_now=False)
        self.assertEqual(open(f"{self.root}/api/.env").read(), before)          # issue: places untouched
        self.assertEqual(self.run_(core.revoke, self.ctx(), [secret]), 0)
        self.assertTrue(self.store.read(*secret).previous)                        # not revoked before apply
        self.run_(core.apply, self.ctx(), [secret])
        self.assertIn(self.store.read(*secret).fields["credential"], open(f"{self.root}/api/.env").read())

    def test_arrange_one_vault_per_environment(self):
        from rekey_lib.arrange import arrange
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = (V, "api.self.auth-secret")
        self.run_(core.rotate, self.ctx(), [secret])                      # a record that has to move along
        os.renames(f"{self.home}/targets/api/file/api/.env.tpl", f"{self.home}/targets/file/api/.env.tpl")   # the flat layout
        self.run_(arrange, self.ctx(), "Test - {env}")
        self.assertTrue(os.path.exists(f"{self.home}/targets/api/file/api/.env.tpl"))     # back in its project folder
        ctx = self.ctx()
        self.assertEqual({v for v, _n in ctx.items()}, {"Test - Local"})       # only .env files here
        self.assertIn(("Test - Local", "api.openai"), ctx.items())
        moved = [n for v, n in ctx.items() if ".self." in n and ctx.read(v, n)]
        self.assertTrue(moved)                                              # the 1Password record moved too
        self.run_(core.sync, ctx, ctx.templates)                           # and every reference still resolves
        names = [n for _v, n in ctx.items()]
        self.assertEqual(len(names), len(set(names)))                      # no two keys collapsed into one

    def test_revoke_sees_the_old_value_under_another_name(self):
        from rekey_lib.arrange import arrange
        from rekey_lib.store import Record
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        self.run_(arrange, self.ctx(), "Test - {env}")                     # web.openai and api.openai: same old value
        ctx = self.ctx()
        api = ("Test - Local", "api.openai")
        self.store.write(*api, Record({"credential": "sk-new-0123456789abcdef"}, previous={"credential": OPENAI},
                                      state={"revoke": {}, "applied": True}), [])
        self.run_(core.sync, ctx, ctx.users(api), item=api, values={"credential": "sk-new-0123456789abcdef"})
        self.assertEqual(self.run_(core.revoke, self.ctx(), [api]), 1)   # web still uses it: refused
        self.assertIn("file/web/.env.local OPENAI_API_KEY", self.out.getvalue())

    def test_init_one_file_adds_only_what_is_missing(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        write(f"{self.root}/api/.env", f"OPENAI_API_KEY={OPENAI}\nRUNNER_AUTH_SECRET=old-auth-secret-1\nPORT=3000\nSTRIPE_API_KEY=sk_test_abc123456789\n")
        self.run_(init, self.ctx(), vault=None, sources=[], tags={}, retire=[], paths=[f"{self.root}/api/.env"], settings=True)
        t = self.ctx().template("file/api/.env")
        self.assertEqual(t.lines["PORT"], "3000")                                   # --with-settings
        self.assertIn("op://Test Vault/api.openai/credential", t.lines["OPENAI_API_KEY"])   # same value → same key
        self.assertIn("STRIPE_API_KEY", t.lines)                                     # the new key was added
        self.assertFalse(os.path.exists(f"{self.home}/targets/web/file/web/.env.local.tpl.bak"))


class Clipboard(unittest.TestCase):
    def test_only_key_shaped_copies_move_on(self):
        from rekey_lib.providers import looks_like_key
        for v in ("482913", "12345678901234567890", "jin@example.com", "Sign in to continue", "short-token"):
            self.assertFalse(looks_like_key(v), v)
        for v in ("a3f9c2e1b7d84f6a9c0e", "pk_7Hq2xLm9Vw3Rt8Zy\n", "-----BEGIN PRIVATE KEY-----\nMIGT\n-----END PRIVATE KEY-----"):
            self.assertTrue(looks_like_key(v), v)
        self.assertFalse(looks_like_key("482913", "re_"))
        self.assertTrue(looks_like_key("re_abc", "re_"))


class Home(unittest.TestCase):
    def test_finds_the_team_data_folder_from_anywhere_inside(self):
        from rekey_lib.cli import find_home
        env = os.environ.pop("REKEY_HOME", None)
        try:
            data = tempfile.mkdtemp()
            os.makedirs(f"{data}/targets/file/x")
            self.assertEqual(find_home(f"{data}/targets/file/x"), data)
            empty = tempfile.mkdtemp()
            self.assertEqual(find_home(empty), empty)          # a new folder for `rekey init`
            os.environ["REKEY_HOME"] = empty
            self.assertEqual(find_home(f"{data}/targets"), empty)
        finally:
            os.environ.pop("REKEY_HOME", None)
            if env:
                os.environ["REKEY_HOME"] = env


class Messages(unittest.TestCase):
    def test_nothing_shadows_the_translator(self):
        """A local variable named _ hides the _() function and breaks messages in that function."""
        import ast
        import glob
        bad = []
        for f in glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rekey_lib", "*.py")):
            for fn in ast.walk(ast.parse(open(f).read())):
                if isinstance(fn, ast.FunctionDef):
                    for n in ast.walk(fn):
                        targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.For) else []
                        if any(isinstance(x, ast.Name) and x.id == "_" for t in targets for x in ast.walk(t)):
                            bad.append(f"{os.path.basename(f)}:{n.lineno} in {fn.name}()")
        self.assertEqual(bad, [])

    def test_every_message_is_translated(self):
        import ast
        import glob
        import re
        from rekey_lib.init import NOTES
        from rekey_lib.messages import ROWS

        rows = {r[0]: r for r in ROWS}
        used = set(NOTES.values())
        for f in glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rekey_lib", "*.py")):
            for n in ast.walk(ast.parse(open(f).read())):
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_" and n.args and isinstance(n.args[0], ast.Constant):
                    used.add(n.args[0].value)
        self.assertEqual(sorted(used - set(rows)), [], "messages without a translation row")
        self.assertEqual(sorted(set(rows) - used), [], "translation rows no code uses")
        for row in ROWS:
            holes = [sorted(re.findall(r"\{(\w+)\}", text)) for text in row]
            self.assertTrue(all(h == holes[0] for h in holes), f"placeholders differ: {row[0]}")

    def test_each_language_speaks(self):
        import subprocess
        rekey = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rekey")
        for lang, word in (("en", "list keys"), ("ko", "키 목록"), ("zh", "列出密钥"), ("ja", "キーの一覧"), ("es", "lista las claves")):
            out = subprocess.run([rekey, "--help"], capture_output=True, text=True, env={**os.environ, "REKEY_LANG": lang}).stdout
            self.assertIn(word, out, lang)
        out = subprocess.run([rekey, "--help"], capture_output=True, text=True,
                             env={k: v for k, v in os.environ.items() if k != "REKEY_LANG"} | {"LANG": "ja_JP.UTF-8"}).stdout
        self.assertIn("キーの一覧", out)


if __name__ == "__main__":
    unittest.main()
