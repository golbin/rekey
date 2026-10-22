# Someone left the team

**1. Remove their access first**, before changing keys:
- 1Password vaults, the GitHub org, and each platform team (Vercel, Railway, Supabase, GCP…)

**2. Rotate the keys they could see.**

```bash
rekey rotate all                                  # they had the whole vault
rekey rotate 'in:vercel/shop/*' 'in:file/shop/*'  # they only worked on some projects
```

With many keys, let the automatic ones finish and press `q` at the browser steps. Continue later with the command rekey prints.

**3. Remove keys they created.** In each service's key list, delete keys they made. Keys made by rekey are named `rekey_…`.
