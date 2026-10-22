"""Drives rekey in a pseudo-terminal like a person: the browser step, then revoke.
Uses the real clipboard (saved and restored), so it runs only when asked:

    REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py
"""

import os
import pty
import re
import subprocess
import sys
import tempfile
import time
import unittest

REKEY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rekey")
OLD, NEW = "up_OLDKEY_1234567890abcdef", "up_NEWKEY_abcdefghijklmnop1234"


@unittest.skipUnless(os.environ.get("REKEY_TEST_CLIPBOARD") and sys.platform == "darwin", "uses the clipboard")
class Person(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(f"{self.root}/rekey/targets/file/app")
        with open(f"{self.root}/app.env", "w") as f:
            f.write(f"UPSTAGE_API_KEY={OLD}\n")
        with open(f"{self.root}/rekey/targets/file/app.env.tpl", "w") as f:
            f.write("UPSTAGE_API_KEY={{ op://V/upstage.app/credential }}\n")
        self.saved = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout

    def tearDown(self):
        subprocess.run(["pbcopy"], input=self.saved, text=True)

    def spawn(self, *args):
        env = dict(os.environ, REKEY_HOME=f"{self.root}/rekey", REKEY_ROOT=self.root, REKEY_STORE=f"file:{self.root}/store.json",
                   REKEY_NO_BROWSER="1", NO_COLOR="1", REKEY_LANG="en")
        pid, self.fd = pty.fork()
        if pid == 0:
            os.execve(REKEY, ["rekey", *args], env)
        self.out = b""

    def expect(self, pattern, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            try:
                self.out += os.read(self.fd, 4096)
            except OSError:
                break
            if re.search(pattern.encode(), self.out):
                return
        self.fail(f"never saw {pattern!r}:\n{self.out.decode(errors='replace')}")

    def copy(self, text):
        subprocess.run(["pbcopy"], input=text, text=True)

    def test_person(self):
        self.spawn("rotate", "all")
        self.expect("Start")
        os.write(self.fd, b"\n")
        self.expect("moves on at once")
        self.assertTrue(subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.startswith("rekey-upstage.app-"))
        self.copy(OLD)
        self.expect("That is the old key")
        self.copy(NEW)
        self.expect("Revoke the old keys now")
        os.write(self.fd, b"n\n")
        time.sleep(0.5)
        self.assertNotIn(NEW.encode(), self.out)
        self.assertNotIn(OLD.encode(), self.out)
        with open(f"{self.root}/app.env") as f:
            self.assertEqual(f.read(), f"UPSTAGE_API_KEY={NEW}\n")

        self.spawn("revoke", "all")
        self.expect("Deleted it")
        self.assertIn(b"\xe2\x80\xa6cdef", self.out)        # tells which old key: …cdef
        os.write(self.fd, b"\n")
        self.expect("deletion confirmed")


if __name__ == "__main__":
    unittest.main()
