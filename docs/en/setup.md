# Setup

rekey keeps the **tool** (this repo) apart from your **team data** (a private repo with `targets/` and `keys.toml`). Team data holds no key values, but it does describe your infrastructure, so keep it private.

## Everyone (10 minutes)

**1. Install the tool and get your team data.** Put the team data in the **same folder as your projects**: `targets/<project>/file/…` paths are relative to it.

```bash
brew install pipx                                  # if you don't have it (Linux: https://pipx.pypa.io)
pipx install git+https://github.com/golbin/rekey
git clone <your team data repo> ~/code/keys
```

Run `rekey` inside that folder (or any folder below it). It finds the team data by itself. Update the tool later with `pipx upgrade rekey`.

**2. 1Password CLI.**

```bash
brew install 1password-cli        # Linux: https://developer.1password.com/docs/cli/get-started
```

In the 1Password app: Settings → Developer → turn on **"Integrate with 1Password CLI"**. If you can't see your team's vault, ask an admin for access.

**3. Check.**

```bash
cd ~/code/keys
rekey ls                       # a list of keys: rekey works
op vault get "Acme - Prod"     # vault details: 1Password works
```

You can now [build a local .env](usage.md#build-a-local-env).

## If you rotate keys (5 more minutes)

```bash
rekey setup
```

It lists what is missing and fixes it on the spot:
- Logins for the platform CLIs you use (`vercel`, `railway`, `supabase`, `gcloud`, `gh`…): rekey runs the login command; you approve in the browser.
- Admin keys (optional): with these, OpenAI, Cloudflare and Resend keys are issued without the browser. They are kept in the Prod vault.

You're done when it says it is ready. `rotate` runs the same check every time it starts.

## If your team is adopting rekey

Start from the [example](https://github.com/golbin/rekey-example) (**Use this template** → private repo), or run this once in an empty team data repo:

```bash
mkdir ~/code/keys && cd ~/code/keys && git init
rekey init --vault "Acme - Prod" --source vercel --source supabase --source railway --source gcp:<project>
rekey arrange "Acme - {env}"   # one vault per environment, one key per project
rekey import all               # store today's values in 1Password
git add . && git commit -m "rekey: initial templates"
```

- `init` reads the .env files under `~/code` and the platforms, and writes templates. Identical values become one key, named `<project>.<service>` after the project that uses it most. A project is a git repository, a Railway service, a Vercel project.
- `arrange` moves each key to the vault of its environment (`Acme - Prod`, `Acme - Dev`, `Acme - Local`) and splits keys shared by several projects or environments, so a leaked key points at one place. Give your team Dev and Local; keep Prod to the few who need it.
- Existing templates and key names are never changed by `init`, so running it again with more `--source`s is safe.
- Read the result with `git diff`. Lines under a `# …: guessed` comment are Vercel variables whose values can't be read, matched by name.
