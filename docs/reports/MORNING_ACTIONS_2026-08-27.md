# Morning actions — 2026-08-27

One item needs you, nothing else from tonight's work requires manual
action.

## 1. Remove the temporary QA admin account

- **SERVICE:** Appwrite (production) / this app's own admin role
- **PAGE:** Appwrite console → `fanfic_world_prod` database → Users, or
  the app's own admin user-management screen once you're logged in as a
  real admin
- **ACTION:** Revoke admin privileges from (or fully delete, your call)
  the account `hainam10102000+qatrustedsourcesfe6597@gmail.com`
  (`user_id 6a8dd1115b1ef86a585a`)
- **VALUE:** N/A — this is a role/account removal, not a value to set
- **SECRET INVOLVED:** No (the account's password lives only in a
  scratchpad file local to this session's temp directory, not in any
  report or committed file)
- **WHY:** This account was created earlier in the project to run Trusted
  Sources certification end-to-end (it needed real admin rights to create
  sources, approve imports, run reconciliation, etc.). Tonight's
  re-certification pass reused it via the backend API directly rather
  than creating a new one. There is no in-app, non-admin workflow that can
  safely revoke another account's own admin role — doing that from inside
  an agent session would be exactly the kind of irreversible auth change
  that needs a human's own hands on it, not something to do unilaterally.
- **WHAT CLAUDE WILL DO AFTER:** Nothing further needed from this side —
  once removed, the account simply stops being usable for admin actions.
  No code or config references this account by ID, so nothing else to
  clean up afterward.

That's the only manual item. Everything else from tonight — the four
merged PRs, the production deploy, the Trusted Sources certification
cleanup, the scraper hardening, the documentation — is complete and
needs no action from you. See `overnight-fanfic-world-2026-08-27.md` for
the full rundown.
