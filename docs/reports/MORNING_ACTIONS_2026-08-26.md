# Morning actions — 2026-08-26

Only actions that genuinely need you. No secrets below.

---

### 1. Fix the FAS_ADMIN_USER_IDS mismatch (blocks Trusted Sources live certification)

**SERVICE:** Render
**PAGE:** `fas-prod-api` → Environment
**EXACT FIELD/BUTTON:** `FAS_ADMIN_USER_IDS` value, then the manual "Deploy latest commit" button (this service has `autoDeploy: false`)
**EXACT NON-SECRET VALUE IF APPLICABLE:** the value should include `6a8dd1115b1ef86a585a` (comma-separated if others are already present)
**WHY:** I tested this account against the live API just now — it still logs in with `is_admin: false`, and `/api/health`'s `admin_count` is unchanged from before. Either the value wasn't saved as `6a8dd1115b1ef86a585a` exactly, or the redeploy didn't actually pick up the new env var (Render sometimes needs the manual deploy trigger even after an env var save). I can't tell which from the outside.
**WHAT CLAUDE WILL DO AFTERWARD:** Re-verify the QA account is admin via the normal API, then run the final live-HTTP Trusted Sources certification (known-duplicate case + one non-overlapping source + full pipeline), all without further input from you. Once done, I'll tell you it's safe to remove that user_id again.

---

### 2. Revoke the temporary Appwrite schema API key

**SERVICE:** Appwrite console (`appwrite-dev.fanfic.world`)
**PAGE:** Project `fanfic-world-prod` → API Keys
**EXACT FIELD/BUTTON:** the temporary/schema-migration key created for last session's `novels` index fix (revoke/delete it)
**WHY:** All schema work that needed it is finished and merged (PR #57, #58 from the prior session). It has no further use and was always meant to be temporary.
**WHAT CLAUDE WILL DO AFTERWARD:** Nothing — this key isn't referenced anywhere in code or docs, it was only ever used ad hoc from the operator's machine. Nothing breaks when you revoke it.

---

### 3. (Optional, low priority) Check the Cloudflare frontend deploy

**SERVICE:** Cloudflare Pages
**PAGE:** the `fanfic.world` project's deployments list
**EXACT FIELD/BUTTON:** none — just look
**WHY:** Tonight merged PR #59 (a real, site-wide CSS bug fix — every "glass" panel was rendering unblurred on Chrome/Edge/Firefox) into `main`. I don't know whether this frontend auto-deploys on merge or needs a manual trigger like the Render backend does — this session didn't check. If it auto-deploys, there's nothing to do; if not, the blur fix (and the new cover art, if it depends on a rebuild — it shouldn't, covers are fetched at runtime) won't be visible until a deploy happens.
**WHAT CLAUDE WILL DO AFTERWARD:** If you tell me it needs a manual trigger, I'll note that permanently instead of re-discovering it next time.
