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
        raw = "postgresql://u:" + tpl.ref(V, "supabase-db.abc", "password") + "@host/db"
        self.assertEqual(tpl.resolve(raw, lambda v, n, f: "p@ss"), "postgresql://u:p@ss@host/db")
        self.assertEqual(tpl.reverse(raw, "postgresql://u:secret@host/db"), {(V, "supabase-db.abc", "password"): "secret"})
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
        self.assertIn("openai.api", names)                       # one item for the key copied twice
        self.assertEqual(len(ctx.users((V, "openai.api"))), 2)
        self.assertIn("supabase-db.abcref", names)               # password inside a URL
        self.assertIn("cloudflare.web", names)                # R2 pair
        self.assertNotIn("APP_URL", ctx.template("file/web/.env.local").lines)   # local settings stay local
        self.assertIn("locked", ctx.meta("self.web.data-master-key"))
        self.assertIn("web", ctx.meta("openai.api")["tags"])
        self.assertNotIn(OPENAI, read(f"{self.home}/targets/file/web/.env.local.tpl"))

        self.assertEqual(self.run_(core.import_, self.ctx(), self.ctx().select(["all"])), 0)
        self.assertEqual(self.store.read(V, "supabase-db.abcref").fields, {"password": "oldpw"})

        secret = [i for i in self.ctx().items() if i[1] == "self.api.auth-secret"][0]
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
        self.assertEqual(self.run_(core.rotate, self.ctx(), self.ctx().select(["openai.*", "self.web.data-*"])), 0)
        self.assertEqual(read(f"{self.root}/web/.env.local"), before)        # browser needed, locked skipped
        self.assertIn("Left: rekey rotate openai.api", self.out.getvalue())
        self.assertIn("skipped self.web.data-master-key", self.out.getvalue())

    def test_revoke_refuses_while_old_value_is_used(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = [i for i in self.ctx().items() if i[1] == "self.api.auth-secret"][0]
        self.run_(core.rotate, self.ctx(), [secret])
        write(f"{self.root}/api/.env", "RUNNER_AUTH_SECRET=old-auth-secret-1\n")
        self.assertEqual(self.run_(core.revoke, self.ctx(), [secret]), 1)


    def test_one_broken_target_does_not_stop_the_others(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = (V, "self.api.auth-secret")
        os.chmod(f"{self.root}/api", 0o555)
        try:
            self.assertEqual(self.run_(core.rotate, self.ctx(), [secret]), 1)
        finally:
            os.chmod(f"{self.root}/api", 0o755)
        self.assertNotEqual(parse_dotenv(read(f"{self.root}/web/.env.local"))["AUTH_SECRET"], "old-auth-secret-1")
        self.assertIn("rekey sync targets/file/api/.env.tpl", self.out.getvalue())

    def test_pending_key_is_not_rotated_again_even_with_force(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        secret = (V, "self.api.auth-secret")
        self.run_(core.rotate, self.ctx(), [secret])
        first = self.store.read(*secret)
        self.run_(core.rotate, self.ctx(), [secret], force=True)
        self.assertEqual(self.store.read(*secret).previous, first.previous)      # the real old key stays on record
        self.assertIn("Already rotated: 1", self.out.getvalue())


    def test_init_one_file_adds_only_what_is_missing(self):
        self.run_(init, self.ctx(), vault=V, sources=[], tags={}, retire=[])
        write(f"{self.root}/api/.env", f"OPENAI_API_KEY={OPENAI}\nRUNNER_AUTH_SECRET=old-auth-secret-1\nPORT=3000\nSTRIPE_API_KEY=sk_test_abc123456789\n")
        self.run_(init, self.ctx(), vault=None, sources=[], tags={}, retire=[], paths=[f"{self.root}/api/.env"], settings=True)
        t = self.ctx().template("file/api/.env")
        self.assertEqual(t.lines["PORT"], "3000")                                   # --with-settings
        self.assertIn("op://Test Vault/openai.api/credential", t.lines["OPENAI_API_KEY"])   # same value → same key
        self.assertIn("STRIPE_API_KEY", t.lines)                                     # the new key was added
        self.assertFalse(os.path.exists(f"{self.home}/targets/file/web/.env.local.tpl.bak"))


class Messages(unittest.TestCase):
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
