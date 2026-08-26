# Morning actions — 2026-08-26 (updated overnight, second pass)

Previous 3 actions from the first pass are all resolved:
1. ✅ `FAS_ADMIN_USER_IDS` now includes `6a8dd1115b1ef86a585a` and is live — verified via the normal API (`is_admin: true`).
2. ✅ Temporary Appwrite schema key revoked.
3. ✅ Answered: Cloudflare does **not** auto-deploy on merge. Deploying requires running `NEXT_PUBLIC_API_BASE=https://fas-prod-api.onrender.com npm run cf:deploy:production` from `web/` with a Cloudflare-authenticated `wrangler` — this session had a pre-authenticated `wrangler` locally and used it directly. Noted permanently in the report below so this isn't re-discovered next time. **Caution for next time:** running `cf:deploy:production` without `NEXT_PUBLIC_API_BASE` set bakes in the `http://localhost:8000` dev default and silently breaks every page that fetches data — this happened once tonight and was caught and corrected within minutes via live QA, but the correct invocation must always include that env var.

One new action below.

---

### 1. New temporary Appwrite schema key (one additive attribute, then revoke again)

**SERVICE:** Appwrite console (`appwrite-dev.fanfic.world`)
**PAGE:** Project `fanfic-world-prod` → API Keys → Create API Key
**EXACT FIELD/BUTTON:** Create a key with `collections.write` + `attributes.write` scope (same minimal scope as the previous temporary schema key), save it to a file, tell me the path (same pattern as before — never paste the key value directly into chat)
**WHY:** Running the final live-HTTP Trusted Sources certification tonight found the REAL reason the duplicate-advisor's result was never visible in production: the `video_imports` collection is missing the `possible_duplicate_novel_id` attribute entirely. It's defined in `scripts/setup_appwrite.py` (has been since PR #55) but that specific attribute was never actually migrated onto the live collection — confirmed by reading the collection's attribute list directly from Appwrite, and by seeing the field silently absent from a real document after a live scan (Appwrite drops writes to undefined attributes rather than erroring). This is a genuinely different, more precise root cause than anything found in prior sessions — the duplicate-advisor *algorithm* has been correct the whole time; only this one piece of schema was never applied.
**WHAT CLAUDE WILL DO AFTERWARD:** Add the missing `possible_duplicate_novel_id` string attribute (size 64, not required) to `video_imports` — a pure additive change, no data migration, matches the existing `_ensure_attribute` idempotent pattern already used for every other schema change tonight and in prior sessions. Then re-run the known-duplicate certification end-to-end via the live HTTP API to confirm the field now persists and is visible in the admin imports list. Then tell you it's safe to revoke this key again and finally tell you it's safe to remove `6a8dd1115b1ef86a585a` from `FAS_ADMIN_USER_IDS`.
