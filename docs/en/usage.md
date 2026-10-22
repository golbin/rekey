# Usage

Run commands inside your team data folder. Commands that change things (`rotate`, `revoke`, `sync`, `import`) only show what they would do with `--dry-run`.

## Build a local .env

```bash
rekey sync targets/file/shop/web/.env.local.tpl
```

- Keys are filled in from 1Password. Other lines in the file are left as they are.
- Local templates hold **keys only**. Write local settings (ports and the like) yourself, or copy them from the project's `.env.example`.
- To share a local setting with the team, add a `KEY=value` line to the template. From the next `sync` on, it is written too.

## Turn an existing .env into a template

```bash
rekey init ~/code/shop/web/.env.local                   # one file
rekey init ~/code/shop --with-settings                   # every .env under a folder, plain settings included
```

- Keys become `{{ op://… }}` references. A value that is already a key in your templates reuses that key.
- If the template exists, only the variables it lacks are added; lines you edited stay as they are.
- Without `--with-settings`, plain settings (ports, URLs…) are left out of local templates.
- Then `rekey import` stores the new values in 1Password.

## Find keys

```bash
rekey ls                     # everything: service, how it is issued, number of places, tags
rekey ls 'openai.*'          # some
rekey where openai.shop      # the templates and variables that use this key
```

## Rotate a key

```bash
rekey rotate openai.shop
```

1. Preflight: anything missing, such as a login, is fixed on the spot.
2. A summary of what will happen, then it asks to start.
3. The new key:
   - **Automatic:** issued by API or generated locally. If that fails (for example, no permission), rekey shows why and switches to the browser.
   - **Browser:** a page opens. Paste the name into the name field with ⌘V (it is already on your clipboard), create the key, and **copy** it. rekey moves on the moment you copy. Press `s` to skip or `q` to stop.
   - Copying the old key, or a key of another service, is caught. If the new key doesn't work, you can copy again.
   - Stopped halfway? Run the same command again: keys already done are skipped. A new key went in wrong? `rekey rotate <key> --redo`.
   - Changed your mind before revoking? `rekey undo <key>` puts the old key back everywhere and deletes the new one.
4. It is saved in 1Password. The old value is kept until it is revoked.
5. Every place is updated. Then rekey asks, service by service, whether to redeploy it now (default: no); the ones you say yes to are watched until healthy.
   - Answer N when a restart would drop live sessions: deploy later your usual way, or `rekey deploy <template>`.
   - Supabase Edge Functions, Fly and Workers apply at once. GitHub Actions use it from the next run.
   - **Services that read GCP Secret Manager need a restart** to pick up the new key.
6. rekey asks whether to revoke the old key now. Answer N to watch a little longer, then later:

```bash
rekey revoke openai.shop
```

- If the old value is still used somewhere, revoke stops and prints the command to run.
- For services without a revoke API, rekey shows the last four characters of the old key and opens the page.
- If anything is interrupted, run the same command again: it continues with what is left. A rotated key is not rotated again until its old key is revoked.
- If some places can't be written, the rest still go ahead, and the command to retry them is printed at the end.

## Many keys at once

```bash
rekey rotate 'cartesia.*'              # by name
rekey rotate tag:breach-2026           # by a tag in keys.toml
rekey rotate 'in:vercel/shop/*'        # every key these templates use
rekey rotate project:shop          # every key one project uses (its repo, Railway service, Vercel project…)
rekey rotate tag:breach-2026 --only openai   # narrow down: a service, a project (in:…), a tag
```

Automatic keys go first; browser steps come last, grouped by service.

### One key per project

When many projects share one key, a leak doesn't tell you where it came from, and every project changes. Split it:

```bash
rekey split 'cartesia.*'      # cartesia.shop → cartesia.shop, cartesia.blog, …
rekey rotate 'cartesia.*'     # each project gets its own key
```

Keys that must stay one value are left alone: your own service-to-service tokens, database passwords and locked keys.

## Change settings

Platform templates also hold plain settings.

```bash
# edit targets/vercel/shop/production.tpl, then
rekey diff targets/vercel/shop/production.tpl            # compare with what is live
rekey sync targets/vercel/shop/production.tpl --deploy   # write it and redeploy
git commit -am "shop: change APP_URL"
```

`sync all` writes to every platform. Use it only when you mean it.

## Add a key

1. Add a line to each template that should get it. Name keys `<service>.<project>`; tokens your own apps share are `self.<project>.<purpose>`.
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/stripe.shop/credential }}
   ```
2. Give it a value: `rekey import stripe.shop` if the value is already in use, or `rekey rotate stripe.shop` to issue a new one.
3. `git commit`

To stop using a key somewhere, delete its line.

## Reference

**Template path = where the values go** (under `targets/`, without `.tpl`)

| Path | Target |
|---|---|
| `file/<path>` | a local file (relative to the folder that holds your team data folder) |
| `vercel/<project>/<production·preview·development>` | Vercel |
| `railway/<project>/<environment>/<service>` | Railway |
| `supabase/<project ref>` | Supabase Edge Function secrets |
| `gcp/<project>` | GCP Secret Manager |
| `github/<owner>/<repo>[/<environment>]` | GitHub Actions secrets |
| `fly/<app>`, `worker/<name>` | Fly, Cloudflare Workers |

Only the variables in a template are written. Nothing else at the target changes.

**keys.toml** lists exceptions only:

```toml
["self.shop.data-master-key"]
locked = "why"                  # rotate skips it (only --force overrides)
note = "read before rotating"   # shown by rotate and where
tags = ["check", "retire"]      # check: rotate skips it / retire: left out of "all"
page = "https://…"              # page to open in the browser step
```

**Admin keys**: items `rekey.openai-admin`, `rekey.cloudflare-admin`, `rekey.resend-admin` and `rekey.anthropic-admin` (for revoking) in the same vault make those services automatic. `rekey setup` helps you add them.

**Environment**: `REKEY_HOME` (team data folder; default: the nearest folder up from here with `targets/` or `keys.toml`), `REKEY_ROOT` (base folder for `file/`, defaults to the parent of `REKEY_HOME`), `REKEY_STORE=file:<path>` (a file instead of 1Password, for testing), `REKEY_NO_BROWSER=1`, `REKEY_LANG` (en, ko, zh, ja, es)
