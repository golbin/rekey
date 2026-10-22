# A key leaked

A key ended up in a commit, a log or a screenshot.

```bash
rekey where <key name>      # don't know the name? try rekey ls '*.openai' or rekey ls project:shop
rekey rotate <key name>
```

Redeploy each service when asked, then **answer y to revoking the old key now**: there is no reason to wait with a leaked key. If rekey didn't ask, some places failed or weren't redeployed: fix them with the command it printed, deploy, then run `rekey revoke <key name>`.

Then:
- A key left in git history is already revoked, so there is no need to rewrite history. If the repo was public, check the service's usage logs for calls you don't recognize.
- If you also put the key somewhere rekey doesn't know (another repo, a personal machine, a third-party dashboard), change it there too and add that place to a template.
