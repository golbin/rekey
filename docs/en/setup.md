# Setup

rekey keeps the **tool** (this repo) apart from your **team data** (a private repo with `targets/` and `keys.toml`). Team data holds no key values, but it does describe your infrastructure, so keep it private.

## Everyone (10 minutes)

**1. Get the tool and your team data.** Put the team data in the **same folder as your projects**: `targets/file/…` paths are relative to it.

```bash
git clone https://github.com/golbin/rekey.git ~/tools/rekey
git clone <your team data repo> ~/code/keys
```

Add to `~/.zshrc` (or `~/.bashrc`) and open a new terminal:

```bash
export REKEY_HOME=~/code/keys
alias rekey=~/tools/rekey/rekey
```

**2. 1Password CLI.**

```bash
brew install 1password-cli        # Linux: https://developer.1password.com/docs/cli/get-started
```

In the 1Password app: Settings → Developer → turn on **"Integrate with 1Password CLI"**. If you can't see your team's vault, ask an admin for access.

**3. Check.**

```bash
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
- Admin keys (optional): with these, OpenAI, Cloudflare and Resend keys are issued without the browser.

You're done when it says it is ready. `rotate` runs the same check every time it starts.

## If your team is adopting rekey

Run once, in an empty team data repo:

```bash
mkdir ~/code/keys && cd ~/code/keys && git init
rekey init --vault "Acme - Prod" --source vercel --source supabase --source railway --source gcp:<project>
rekey import all        # store today's values in 1Password
git add . && git commit -m "rekey: initial templates"
```

- `init` reads the .env files under `~/code` and the platforms, and writes templates. Identical values become one key.
- If a folder holds several projects (e.g. `~/code/clients/a`, `~/code/clients/b`), add `--group-dirs clients` so keys are named after the folders inside it.
- Existing templates and key names are never changed, so running it again with more `--source`s is safe.
- Read the result with `git diff`. Lines under a `# … 추정` ("guessed") comment are Vercel variables whose values can't be read, matched by name.
