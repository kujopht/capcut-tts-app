#!/usr/bin/env python3
"""Mission G, Track 1 — Ngoc Huyen (Moi) TTS proof for ONE already-created
production chapter:

    novel_id:   nov_1e38f5532fab4681
    chapter_id: chp_f3737aeae1f749db   (Chuong 1, Re: Zero fanfic)
    voice_id:   piper:ngochuyennew     ("Ngoc Huyen (Moi)")

Reads `FAS_HARVESTER_TOKEN` from this process's OWN environment at
execution time. NEVER prints/logs/writes the token - same `goi()` pattern
as `scripts/mission_g_rezero_draft_runner.py`. Run it FROM the shell that
already holds the token:

    .venv\\Scripts\\python.exe scripts\\mission_g_rezero_tts_runner.py

    # preview only (no token needed, creates nothing):
    .venv\\Scripts\\python.exe scripts\\mission_g_rezero_tts_runner.py --dry-run

WHAT THIS PROVES, AND WHY POLLING IS THE ONLY HONEST TEST: `GET /api/voices`
reports Piper voices' status via a HARDCODED constant
(`tts_bridge.WORKER_STATUS = "worker"`), not a live health check - see that
file's own comment on why (avoids a disk read on every /api/voices call).
There is no real signal for "is the laptop worker actually connected"
short of creating a real job and watching whether a worker claims it
(`TtsJob.lease_expires_at` moving from absent -> a real future timestamp
is that signal - `TtsJob.lease_is_live()` in server/domain.py).

If polling times out with the job still `pending` and no lease ever
observed, this script STOPS and prints the exact command to start the
worker (`python -m server.worker`, per that module's own docstring) - it
does not guess or wait longer, and it never touches worker/Appwrite/R2
credentials itself (those live wherever the worker is meant to run, not
here).

Boundaries, enforced by construction:
  - Only POST /api/jobs (create) and GET reads - never PUT/PATCH/DELETE,
    never /publish, never touches any Novel/Chapter/Job other than the
    one chapter_id hardcoded above.
  - `voice_id` is a literal constant, never derived/guessed/registered -
    this script cannot create or select a different voice.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_API = "https://fas-prod-api.onrender.com"
TOKEN_ENV_VAR = "FAS_HARVESTER_TOKEN"

CHAPTER_ID = "chp_f3737aeae1f749db"
VOICE_ID = "piper:ngochuyennew"
VOICE_DISPLAY_NAME_EXPECTED = "Ngọc Huyền (Mới)"

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 240  # generous: Render free-tier cold start + real synthesis

KET_QUA = []


def kt(ten: str, dieu_kien: Any, ghi_chu: str = "") -> bool:
    ok = bool(dieu_kien)
    KET_QUA.append((ten, ok, ghi_chu))
    print(f"  [{'PASS' if ok else 'FAIL'}] {ten}" + (f" -- {ghi_chu}" if ghi_chu else ""),
          flush=True)
    return ok


def goi(api: str, method: str, path: str, payload: Any = None,
        token: Optional[str] = None, timeout: int = 60) -> Tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(api.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "mission-g-rezero-tts-runner/1.0")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"raw": body[:500]}
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)}


def fetch_bytes_headers(url: str, timeout: int = 30) -> Tuple[int, Dict[str, str]]:
    """Real GET on the signed playback URL - no token needed, it's pre-signed.
    Returns (status, headers) without reading/keeping the full audio body."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(4096)  # enough to prove real bytes stream, not a huge download
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {})
    except Exception:
        return 0, {}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--api", default=DEFAULT_API)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    print(f"Mission G TTS runner\n  api={a.api}\n  chapter_id={CHAPTER_ID}\n"
          f"  voice_id={VOICE_ID}\n  dry_run={a.dry_run}")

    print("\n=== 1. Confirm the voice as exposed by the real production /api/voices ===")
    ma, r = goi(a.api, "GET", "/api/health")
    if not kt("GET /api/health -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    voices_url = a.api.rstrip("/") + "/api/voices"
    ma2, r2 = 0, {}
    try:
        with urllib.request.urlopen(voices_url, timeout=30) as resp:
            r2 = json.loads(resp.read().decode("utf-8"))
            ma2 = resp.status
    except Exception as exc:
        kt("GET /api/voices -> 200", False, f"{type(exc).__name__}: {exc}")
        return 1
    kt("GET /api/voices -> 200", ma2 == 200, f"HTTP {ma2}")
    voice_entry = next((v for v in r2.get("voices", []) if v.get("voice_id") == VOICE_ID),
                        None)
    if not kt(f"voice_id {VOICE_ID!r} present in /api/voices", voice_entry is not None):
        return 1
    kt("display_name matches 'Ngọc Huyền (Mới)' (the NEW voice, not the old one)",
       voice_entry.get("display_name") == VOICE_DISPLAY_NAME_EXPECTED,
       f"display_name={voice_entry.get('display_name')!r}")
    kt("provider is piper (local/worker-run, not a different engine)",
       voice_entry.get("provider") == "piper", f"provider={voice_entry.get('provider')}")

    if a.dry_run:
        print("\n--dry-run: would POST /api/jobs for this chapter+voice. Stopping here.")
        return 0

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"\nBLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.",
              file=sys.stderr)
        return 2

    print("\n=== 2. Check for an existing job for this chapter+voice (idempotent) ===")
    ma, r = goi(a.api, "GET", f"/api/chapters/{CHAPTER_ID}/jobs/latest", token=token)
    job_id = ""
    if ma == 200 and (r.get("job") or {}).get("voice_id") == VOICE_ID \
            and (r.get("job") or {}).get("status") in ("pending", "running", "completed"):
        job_id = r["job"]["job_id"]
        kt("reusing existing job (no duplicate created)", True,
           f"job_id={job_id} status={r['job']['status']}")
    else:
        print("\n=== 3. Create the TTS job (POST /api/jobs) ===")
        ma, r = goi(a.api, "POST", "/api/jobs", {
            "chapter_id": CHAPTER_ID, "voice_id": VOICE_ID,
            "rate": "1.0", "chunk_chars": 2000,
        }, token=token)
        if not kt("POST /api/jobs -> 201", ma == 201, f"HTTP {ma}: {r}"):
            return 1
        job = r.get("job") or r
        job_id = job.get("job_id", "")
        if not kt("received job_id", bool(job_id)):
            return 1

    print(f"\n=== 4. Poll job {job_id} for up to {POLL_TIMEOUT_SECONDS}s "
          f"(every {POLL_INTERVAL_SECONDS}s) ===")
    saw_live_lease = False
    final_job: Dict[str, Any] = {}
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        ma, r = goi(a.api, "GET", f"/api/jobs/{job_id}", token=token)
        if ma != 200:
            print(f"    poll HTTP {ma}, retrying...")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        job = r.get("job") or {}
        final_job = job
        st = job.get("status")
        if job.get("lease_expires_at"):
            saw_live_lease = True
        print(f"    status={st} progress={job.get('progress')}% "
              f"lease={'yes' if job.get('lease_expires_at') else 'no'}")
        if st in ("completed", "failed"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if final_job.get("status") not in ("completed", "failed") and not saw_live_lease:
        print(f"\nBLOCKED: job {job_id} is still {final_job.get('status')!r} after "
              f"{POLL_TIMEOUT_SECONDS}s, and no worker ever claimed it (lease_expires_at "
              f"never set). The laptop Piper worker is not running/connected.")
        print("\nExact command to start it (run in your own trusted shell, with real "
              "production Appwrite/R2 credentials already configured there - this "
              "script never touches those):")
        print('  $env:FAS_ENV_FILE = "server\\.env.production"')
        print("  .venv\\Scripts\\python.exe -m server.worker --require-env production")
        print(f"\nThen re-run this script - it will reuse job {job_id} instead of "
              "creating a duplicate.")
        return 3

    if not kt("job reached a terminal state", final_job.get("status") in ("completed", "failed"),
              f"status={final_job.get('status')}"):
        return 1
    if not kt("job status == completed (not failed)", final_job.get("status") == "completed",
              f"error_kind={final_job.get('error_kind')} "
              f"error_message={final_job.get('error_message')!r}"):
        return 1
    kt("output_key set", bool(final_job.get("output_key")),
       f"output_key={final_job.get('output_key')}")

    print("\n=== 5. Read the resulting AudioTrack (GET /api/chapters/{id}) ===")
    ma, r = goi(a.api, "GET", f"/api/chapters/{CHAPTER_ID}", token=token)
    if not kt("GET /api/chapters/{id} -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    audio = r.get("audio") or {}
    kt("AudioTrack present", bool(audio))
    kt("voice_id on track == piper:ngochuyennew", audio.get("voice_id") == VOICE_ID,
       f"voice_id={audio.get('voice_id')}")
    kt("duration_seconds > 0", (audio.get("duration_seconds") or 0) > 0,
       f"duration_seconds={audio.get('duration_seconds')}")
    kt("size_bytes > 0", (audio.get("size_bytes") or 0) > 0,
       f"size_bytes={audio.get('size_bytes')}")

    print("\n=== 6. Verify real playback path (GET /api/audio/{id}/url + fetch bytes) ===")
    ma, r = goi(a.api, "GET", f"/api/audio/{CHAPTER_ID}/url", token=token)
    if not kt("GET /api/audio/{id}/url -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    play_url = r.get("url") or r.get("stream_url")
    kt("received a playable URL", bool(play_url))
    if play_url and play_url.startswith("http"):
        pma, headers = fetch_bytes_headers(play_url)
        kt("signed R2 URL returns real audio bytes", pma == 200,
           f"HTTP {pma} content-type={headers.get('Content-Type')}")
    else:
        kt("skipped raw-bytes fetch (relative stream_url needs auth header, "
           "covered by /api/audio/{id} route separately)", True)

    so_dat = sum(1 for _, ok, _ in KET_QUA if ok)
    so_tong = len(KET_QUA)
    print(f"\n=== SUMMARY: {so_dat}/{so_tong} checks PASS ===")
    print(f"job_id: {job_id}")
    print(f"voice_id: {VOICE_ID}")
    print(f"provider/model: piper (NghiTTS Piper voice, worker-hosted)")
    print(f"duration_seconds: {audio.get('duration_seconds')}")
    print(f"size_bytes: {audio.get('size_bytes')}")
    print(f"storage object_key: {audio.get('object_key')}")
    print(f"content_hash: {audio.get('content_hash')}")
    for ten, ok, ghi_chu in KET_QUA:
        if not ok:
            print(f"  FAIL: {ten} -- {ghi_chu}")

    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())
