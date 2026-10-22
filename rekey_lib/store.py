"""Where values live. One item per key:

    fields             current values ("credential", "password", ...)
    section previous   values before the last rotation, kept until the old key is revoked
    section rekey      one JSON field: issued_at, issued_by, meta (ids needed to revoke later),
                       revoke (meta of the previous key while it waits to be revoked)
"""

from __future__ import annotations

import datetime as dt
import getpass
import json
import os
from dataclasses import dataclass, field
from typing import Any

from .i18n import _
from .util import RekeyError, have, private_file, run


@dataclass
class Record:
    fields: dict[str, str] = field(default_factory=dict)
    previous: dict[str, str] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)

    def stamp(self) -> None:
        self.state["issued_at"] = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")
        self.state["issued_by"] = os.environ.get("REKEY_USER") or getpass.getuser()


class OnePassword:
    label = "1Password"

    def check(self) -> str | None:
        if not have("op"):
            return _("Install the 1Password CLI: brew install 1password-cli")
        try:
            if run(["op", "vault", "list"], check=False, timeout=10).returncode == 0:
                return None
        except RekeyError:
            pass
        return _("In the 1Password app: Settings → Developer → turn on 'Integrate with 1Password CLI'")

    def has_vault(self, vault: str) -> bool:
        return run(["op", "vault", "get", vault], check=False, timeout=30).returncode == 0

    def create_vault(self, vault: str) -> None:
        run(["op", "vault", "create", vault], timeout=60)

    def _get(self, vault: str, name: str) -> dict | None:
        p = run(["op", "item", "get", name, "--vault", vault, "--format", "json", "--reveal"], check=False, timeout=30)
        if p.returncode:
            if "isn't an item" in p.stderr or "not found" in p.stderr.lower():
                return None
            raise RekeyError(_("couldn't read {name} from 1Password:", name=name) + " " + p.stderr.strip()[-150:])
        return json.loads(p.stdout)

    def read(self, vault: str, name: str) -> Record | None:
        item = self._get(vault, name)
        return None if item is None else self._record(item)

    def read_all(self, vault: str) -> dict[str, Record]:
        """Every item in the vault, in two op calls instead of one per item."""
        listed = run(["op", "item", "list", "--vault", vault, "--format", "json"], timeout=60).stdout
        if not json.loads(listed or "[]"):
            return {}
        out = run(["op", "item", "get", "-", "--reveal", "--format", "json"], stdin=listed, timeout=300).stdout
        items, i, out = {}, 0, out.strip()
        while i < len(out):                                   # op prints one JSON object after another
            item, i = json.JSONDecoder().raw_decode(out, i)
            items[item["title"]] = self._record(item)
            i += len(out[i:]) - len(out[i:].lstrip())
        return items

    @staticmethod
    def _record(item: dict) -> Record:
        rec = Record()
        for f in item.get("fields", []):
            section, label, value = (f.get("section") or {}).get("id"), f.get("label"), f.get("value")
            if not value:
                continue
            if section == "previous":
                rec.previous[label] = value
            elif section == "rekey":
                rec.state = json.loads(value)
            elif f.get("type") == "CONCEALED":
                rec.fields[label] = value
        return rec

    def write(self, vault: str, name: str, rec: Record, tags: list[str]) -> None:
        def f(label: str, value: str, section: str | None = None, kind: str = "CONCEALED") -> dict:
            d = {"id": f"{section}.{label}" if section else label, "type": kind, "label": label, "value": value}
            return {**d, "section": {"id": section}} if section else d

        item = {
            "title": name,
            "category": "API_CREDENTIAL",
            "tags": sorted({"rekey", *tags}),
            "sections": [{"id": "previous", "label": "previous (waiting to be revoked)"}, {"id": "rekey", "label": "rekey"}],
            "fields": [f(k, v) for k, v in rec.fields.items()]
                      + [f(k, v, "previous") for k, v in rec.previous.items()]
                      + [f("state", json.dumps(rec.state, ensure_ascii=False), "rekey", "STRING")],
        }
        existing = self._get(vault, name)
        with private_file(json.dumps(item), ".json") as path:
            if existing:
                run(["op", "item", "edit", existing["id"], "--vault", vault, "--template", path], timeout=60)
            else:
                run(["op", "item", "create", "--vault", vault, "--template", path], timeout=60)


class FileStore:
    """A 0600 JSON file. For tests and for trying rekey without 1Password."""

    label = _("local file store")

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
            return json.load(f)

    def check(self) -> str | None:
        return None

    def has_vault(self, vault: str) -> bool:
        return True

    def create_vault(self, vault: str) -> None:
        pass

    def read(self, vault: str, name: str) -> Record | None:
        d = self._load().get(f"{vault}/{name}")
        return Record(**d) if d else None

    def read_all(self, vault: str) -> dict[str, Record]:
        return {k.split("/", 1)[1]: Record(**d) for k, d in self._load().items() if k.startswith(vault + "/")}

    def write(self, vault: str, name: str, rec: Record, tags: list[str]) -> None:
        data = self._load()
        data[f"{vault}/{name}"] = rec.__dict__
        fd = os.open(self.path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(self.path + ".tmp", self.path)


def open_store() -> OnePassword | FileStore:
    spec = os.environ.get("REKEY_STORE", "")
    return FileStore(spec[5:]) if spec.startswith("file:") else OnePassword()
