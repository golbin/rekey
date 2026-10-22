# Usage

Run commands inside your team data folder. Commands that change things (`rotate`, `issue`, `revoke`, `sync`, `import`, `arrange`) only show what they would do with `--dry-run`.

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
- Then `rekey arrange "Acme - {env}"` files new keys under the right vault, and `rekey import` stores their values in 1Password.

## Find keys

```bash
rekey ls                     # everything: service, how it is issued, number of places, tags
rekey ls project:shop        # one project
rekey ls '*.openai'          # one service
rekey where shop.openai      # the templates and variables that use this key
```

## Rotate a key

```bash
rekey rotate shop.openai
```

1. Preflight: anything missing, such as a login, is fixed on the spot.
2. A summary of what will happen, then it asks to start.
3. The new key:
   - **Automatic:** issued by API or generated locally. If that fails (for example, no permission), rekey shows why and switches to the browser.
   - **Browser:** a page opens with what to click. Paste the name into the name field with ⌘V (it is already on your clipboard), give the key the same permissions as the old one (its last four characters are shown), create it, and **copy** it. rekey moves on the moment you copy. Press `s` to skip or `q` to stop.
   - Sign-in codes, the old key, or a key of another service are not taken for the new key.
   - A database password comes last: the old one stops working the moment the new one is saved.
4. It is saved in 1Password. The old value is kept until it is revoked.
5. Every place is updated. Then rekey asks, service by service, whether to redeploy it now (default: no). Answer N when a restart would drop live sessions, and deploy later your usual way or with `rekey deploy <template>`.
   - Supabase Edge Functions, Fly and Workers apply at once. GitHub Actions use it from the next run.
   - **Services that read GCP Secret Manager need a restart** to pick up the new key.
6. Once every service has been redeployed, rekey asks whether to revoke the old key now. Otherwise, after your deploys:

```bash
rekey revoke shop.openai
```

- Revoke refuses while a place still holds the old value. It reads the variables, not what a running service has loaded, so revoke only after the deploys.
- For services without a revoke API, rekey shows the last four characters of the old key and opens the page.
- If some places can't be written, the rest still go ahead, and the command to retry them is printed at the end.

### Two steps

To look before anything changes, issue first and put the keys in place later:

```bash
rekey issue project:shop     # new keys into 1Password only; no place changes
rekey apply project:shop     # write them everywhere, then each redeploy is asked
```

### When something goes wrong

- **Stopped halfway:** run the same command again. Finished keys are skipped; a rotated key is never rotated again until its old key is revoked.
- **A wrong value went in** (a sign-in code, the wrong key): `rekey rotate <key> --redo` makes the new key again; the original old key stays the one to revoke.
- **Changed your mind before revoking:** `rekey undo <key>` puts the old key back everywhere and, once the services are redeployed, deletes the new one.

## Many keys at once

```bash
rekey rotate project:shop                  # every key one project uses (its repo, Railway service, Vercel project…)
rekey rotate tag:breach-2026               # by a tag in keys.toml
rekey rotate 'in:railway/*'                # every key these templates use
rekey rotate '*.cartesia'                  # by name
rekey rotate tag:breach-2026 --only shop   # narrow down: a project or service, a name, tag:, in:, project:
```

Automatic keys go first; browser steps come next, grouped by service; database passwords come last.

## One vault per environment, one key per project

```bash
rekey arrange "Acme - {env}" --dry-run     # see the plan
rekey arrange "Acme - {env}"
```

- Each key moves to the vault of the environment that uses it: `Acme - Prod`, `Acme - Dev` or `Acme - Local`.
- A key shared by several projects or environments is split, one per project and environment, named `<project>.<service>`. Until the next `rotate` the pieces hold the same value; after it, a leak points at one project.
- Kept whole: your own service-to-service tokens (`.self.`), database passwords, locked keys, and keys waiting to be revoked.
- 1Password items are moved and renamed, never deleted. Review with `git diff`, then commit.
- Team data from before rekey 0.3 names keys `<service>.<project>`; add `--old-names` once to rename them.

## Change settings

Platform templates also hold plain settings.

```bash
# edit targets/vercel/shop/production.tpl, then
rekey diff targets/vercel/shop/production.tpl   # compare with what is live
rekey sync targets/vercel/shop/production.tpl   # write it; the redeploy is asked
git commit -am "shop: change APP_URL"
```

`sync all` writes to every platform. Use it only when you mean it.

## Add a key

1. Add a line to each template that should get it. Name keys `<project>.<service>`; tokens your own apps share are `<project>.self.<purpose>`.
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/shop.stripe/credential }}
   ```
2. Give it a value: `rekey import shop.stripe` if the value is already in use, or `rekey rotate shop.stripe` to issue a new one.
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

Only the variables in a template are written. Nothing else at the target changes. A Railway variable that references another service (`${{ api.OPENAI_API_KEY }}`) is never overwritten: rekey stops and says so.

**Key names**: `<project>.<service>[.<purpose>]`. The service decides how the key is issued (`shop.openai` → OpenAI); `self` means generated by rekey, `other` means a person issues it in the browser.

**keys.toml** lists exceptions only:

```toml
["shop.self.data-master-key"]
locked = "why"                  # rotate skips it (only --force overrides)
note = "read before rotating"   # shown by rotate and where
tags = ["check", "retire"]      # check: rotate skips it / retire: left out of "all"
page = "https://…"              # page to open in the browser step
```

**Admin keys**: items `rekey.openai-admin`, `rekey.cloudflare-admin`, `rekey.resend-admin` and `rekey.anthropic-admin` (for revoking) in any of your vaults, usually Prod, make those services automatic. `rekey setup` helps you add them.

**Environment**: `REKEY_HOME` (team data folder; default: the nearest folder up from here with `targets/` or `keys.toml`), `REKEY_ROOT` (base folder for `file/`, defaults to the parent of `REKEY_HOME`), `REKEY_STORE=file:<path>` (a file instead of 1Password, for testing), `REKEY_NO_BROWSER=1`, `REKEY_LANG` (en, ko, zh, ja, es)
