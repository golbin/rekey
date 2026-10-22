**English** · [한국어](README.ko.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [Español](README.es.md)

# rekey

Reissue an API key with one command, update it everywhere it is used (.env files, Vercel, Railway, Supabase, GCP, GitHub…), and revoke the old one.

```bash
pipx install git+https://github.com/golbin/rekey   # install
rekey rotate 'openai.*'   # new key → every place updated → redeploys checked
rekey revoke 'openai.*'   # old key revoked
```

- You don't need to know each service. Keys that can be issued by API are handled automatically; for the rest, rekey opens the right page and you just make the key and **copy** it.
- Key values never appear on screen. They live only in 1Password.
- Python 3.11+, standard library only.
- Messages follow your system language (English, 한국어, 中文, 日本語, Español). Set `REKEY_LANG=en` to choose.

## How it works

| What | Where |
|---|---|
| Key values | 1Password (one item per key) |
| Where each key is used, plus plain settings | `targets/**.tpl` in your team's private repo |
| Exceptions (locked, tags, notes) | `keys.toml` in your team's private repo |

Templates use 1Password's own syntax, and the file path says where the values go.

```
# targets/vercel/shop/production.tpl  →  Vercel project "shop", production
APP_URL=https://shop.example.com
OPENAI_API_KEY={{ op://Acme - Prod/openai.shop/credential }}
```

## Guides

1. [Setup](docs/en/setup.md): 10 minutes
2. [Usage](docs/en/usage.md)
3. Situations: [A key leaked](docs/en/situations/key-leaked.md) · [A platform was breached](docs/en/situations/platform-breach.md) · [Someone left the team](docs/en/situations/member-left.md)

## Development

```bash
python3 -m unittest discover -s tests
REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py   # drives a real terminal (macOS, uses the clipboard)
```

MIT License
