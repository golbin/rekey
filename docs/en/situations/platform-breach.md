# A platform was breached

Vercel, Railway, Supabase or another platform announced that stored environment variables may have been exposed.

**1. Pick the keys on that platform.**

```bash
rekey ls 'in:railway/*'        # vercel/*, supabase/*, gcp/* … for your platform
```

If the list is empty or looks short, read the platform again to fill in the templates. Existing templates and names are not changed.

```bash
rekey init --vault "Acme - Prod" --source railway
```

If you ever uploaded a whole local .env to that platform, the keys in that .env count too. Just add selectors:

```bash
rekey ls 'in:railway/*' 'in:file/shop/api/*'
```

**2. Rotate them**, with the same selectors. With many keys, go one project at a time:

```bash
rekey rotate 'in:railway/*' 'in:file/shop/api/*' --only project:shop
```

The browser steps follow the automatic ones. Redeploy when asked (or your usual way), then revoke right away: `rekey revoke 'in:railway/*' 'in:file/shop/api/*'`.

On Railway, a variable that references another service (`${{ api.KEY }}`) follows that service: rotate the source, redeploy both.

**3. Clean up the platform side**
- Rotate that platform's account and project tokens as well (the ones CI uses). They are usually in `github/…` templates.
- Check what the platform's GitHub app can access (GitHub → Settings → Applications).
- Delete projects you no longer use.
