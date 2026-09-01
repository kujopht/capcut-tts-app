# SHIP AUDIO + KEEP CONTENT FACTORY MOVING (2026-09-01)

## Track A — TTS worker diagnosis (real root cause found, not fixed)

Inspected in order (no guessing): `_tao_job_cho_chuong` in `server/main.py`
→ found the code's own comment describing `FAS_INLINE_WORKER=false` on
staging/production → found `server/worker.py`, a complete, already-built
separate worker process (claim/lease/heartbeat, `python -m server.worker`)
→ found its deploy target is **systemd on a self-hosted machine**
(`deploy/fanfic-worker.service`), not Render → confirmed via the real
Render service list (only 3 `web_service` entries, no background worker)
→ found the authoritative answer in `deploy/render.prod.yaml`'s own
architecture comment: **"TTS worker trên LAPTOP ← không phải Render"**
(TTS worker on the LAPTOP, not Render) — a documented MVP cost tradeoff,
not a bug. Render Free has no Background Worker tier; audio is only
produced while a human's laptop runs the worker.

Confirmed a worker DID run successfully on this exact machine in an
earlier turn this session (`scripts/mission_g_rezero_tts_runner.py`'s own
docstring records a real measured synthesis: 1792.76s for the Re:Zero
chapter, 2026-08-31) — explaining why that TTS completed and why today's
Naruto jobs did not: `server/.env.production` (the worker's credential
file, used then) no longer exists on this machine.

**Real, hard wall found while trying to fix it**: the Piper voice model
files for `ngochuyennew` have **no declared, verified download source**
anywhere in this repo — `desktop_app/providers/builtin_catalog.py`'s own
comment states this explicitly: "KHONG khai bao URL tai hay SHA-256 o day:
chua xac minh duoc nguon tai on dinh nen tuyet doi khong bia dat" (do not
fabricate a download URL — none has been verified). No `.onnx`/`.onnx.json`
files exist locally either. Getting a real worker synthesizing
`piper:ngochuyennew` on this machine requires the human to place those 2
model files locally — this is not something safe for me to invent a
source for (would mean downloading from an unverified source, and CLAUDE.md
separately forbids auto-switching to a different voice on failure).
**Not fixed this run — genuinely needs a human step.**

## Track B — 10 real Naruto chapters now in production draft

Chapters 8, 9, 10, 11 acquired from the same source
(`narutofanon.fandom.com`, public MediaWiki API), translated EN→VI via
Antigravity, QA'd, shipped to the existing novel `nov_6764055a19c44e63`.
Total: **10 chapters**, all `state=draft`, confirmed not in the public
listing. Two TTS jobs remain queued (`pending`) from earlier — they will
complete automatically once a worker (per Track A) is running.

## Track C — animation subtitle hunt

Checked 3 more candidates including the OFFICIAL Youku Animation channel
(`@youkuanimation`) — 0/3 had real caption tracks. Combined with the prior
run's 28 checked videos, **0 of 31 total AI-animation videos checked this
mission (fan or official) have extractable caption text** — burned-in
subtitles appear to be a genre-wide convention, not a per-channel choice.
No new subtitle-capable source found.

## Test / cost / commits

No server-side code changed this run (only 2 new client-side runner
scripts) — backend suite unchanged at 4249/4249. Cost: $0 (MediaWiki API +
Antigravity, both free). Commits: `bb2c270` (latest).

## What a human needs to do to unblock Track A completely

Place the real `ngochuyennew` Piper `.onnx` + `.onnx.json` files at
`%LOCALAPPDATA%\FanficAudioStudio\models\piper\`, and provide production
Appwrite/R2 credentials once (e.g. recreate `server/.env.production`).
After that, running `python -m server.worker --require-env production` on
this machine will drain the queue automatically — no code changes needed.
