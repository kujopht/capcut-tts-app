"""Browser QA cho trang chuong thong nhat doc/nghe (sprint UX doc/nghe 2026-09-24).

Chay tren BAN BUILD PRODUCTION CUC BO voi chuong THAT (qua proxy CHI DOC
`readonly_proxy.py`) va audio R2 ky THAT. Moi kiem tra ghi PASS/FAIL vao
`<OUT>/results.json`; anh chup vao `<OUT>/*.png`.

Cach chay (Windows, tu goc kho):

    .venv/Scripts/python.exe scripts/qa/reader_ux/readonly_proxy.py 38123
    NEXT_PUBLIC_API_BASE=http://localhost:38123 npm --prefix web run build
    npm --prefix web run start -- -p 3100
    .venv/Scripts/python.exe scripts/qa/reader_ux/run_qa.py            # tat ca
    .venv/Scripts/python.exe scripts/qa/reader_ux/run_qa.py 390x844     # mot khung

Proxy tu choi MOI request ghi (405) — QA khong the lam doi du lieu production
(luot nghe, tien do, binh luan). KHONG dung ban build nay de trien khai: no tro
API ve proxy cuc bo.

`OUT` mac dinh o thu muc tam (`READER_UX_QA_OUT` de doi), khong nam trong kho.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cdp import Browser  # noqa: E402

BASE = os.environ.get("READER_UX_QA_BASE", "http://localhost:3100")
OUT = Path(os.environ.get("READER_UX_QA_OUT", Path(tempfile.gettempdir()) / "reader_ux_qa")) / "after"
CH = {
    "butterfly": ("ch_136586_0002", "ch_136586_0003"),
    "cold": ("ch_156206_0001", "ch_156206_0002"),
    "genshin": ("chp_nov_seed_genshin_hoakhoi_15_0001", "chp_nov_seed_genshin_hoakhoi_15_0002"),
}
VIEWPORTS = [("1600x900", 1600, 900, False), ("1366x768", 1366, 768, False), ("390x844", 390, 844, True)]
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.partial.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
    return ok


AUDIO = "(() => { const a = document.querySelector('audio'); return a ? {paused: a.paused, t: a.currentTime, d: a.duration, src: a.getAttribute('src') || ''} : null })()"
ACTIVE = """(() => { const ps = document.querySelectorAll('.reader-para.is-speaking');
  if (ps.length !== 1) return {n: ps.length};
  const r = ps[0].getBoundingClientRect();
  return {n: 1, idx: +ps[0].dataset.doan, top: r.top, bottom: r.bottom, vh: innerHeight}; })()"""


def audio(b):
    return b.eval(AUDIO)


def fetch_pump(b, seconds, old_url):
    """Service paused R2 requests: the OLD signed URL gets an S3-style 403, others continue."""
    import base64

    import websocket
    served = 0
    end = time.time() + seconds
    while time.time() < end:
        pending = [e for e in b.events if e.get("method") == "Fetch.requestPaused"]
        b.events = [e for e in b.events if e.get("method") != "Fetch.requestPaused"]
        for e in pending:
            p = e["params"]
            if p["request"]["url"] == old_url:
                body = base64.b64encode(b"<Error><Code>AccessDenied</Code><Message>Request has expired</Message></Error>").decode()
                b.send("Fetch.fulfillRequest", {"requestId": p["requestId"], "responseCode": 403,
                                                "responseHeaders": [{"name": "Content-Type", "value": "application/xml"}],
                                                "body": body})
                served += 1
            else:
                b.send("Fetch.continueRequest", {"requestId": p["requestId"]})
        try:
            b.ws.settimeout(0.25)
            b.events.append(json.loads(b.ws.recv()))
        except websocket.WebSocketTimeoutException:
            pass
        finally:
            b.ws.settimeout(60)
    return served


def wait_playing(b, min_t=1.5, timeout=45):
    b.wait(f"(() => {{ const a = document.querySelector('audio'); return a && !a.paused && a.currentTime > {min_t}; }})()",
           timeout=timeout)


def n_audio(b):
    return b.eval("document.querySelectorAll('audio').length")


def overflow(b):
    return b.eval("[document.documentElement.scrollWidth, innerWidth]")


def click_text(b, selector, text):
    return b.eval(f"""(() => {{ const el = [...document.querySelectorAll({json.dumps(selector)})]
      .find(x => x.textContent.includes({json.dumps(text)}) && x.offsetParent !== null);
      if (!el) return false; el.click(); return true; }})()""")


def click_seek(b, frac):
    box = b.eval("""(() => { const s = document.querySelector('.dock .dock-seek-range, .listen-hero .seek');
      if (!s) return null; const r = s.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()""")
    if not box:
        return False
    x, y, w, h = box
    b.click_at(x + 8 + (w - 16) * frac, y + h / 2)
    return True


def in_view(a):
    return a and a.get("n") == 1 and a["top"] >= 0 and a["top"] < a["vh"]


def run_viewport(vname, w, h, mobile):
    b = Browser()
    try:
        b.viewport(w, h, mobile)
        # ---- initial views of all three novels
        for nov, (cid, _) in CH.items():
            b.goto(f"{BASE}/chapters/{cid}", settle=2.0, wait_expr="document.querySelector('.reader-para')", timeout=240)
            b.shot(OUT / f"{vname}_{nov}_01_initial.png")
            check(f"{vname} {nov}: one <audio> element", n_audio(b) == 1, str(n_audio(b)))
            check(f"{vname} {nov}: default mode Doc+Nghe with idle mini dock",
                  b.eval("!!document.querySelector('.reader-mode.is-active') && document.querySelector('.reader-mode.is-active').textContent.includes('Đọc + Nghe') && !!document.querySelector('.dock.dock-mini')"))
            check(f"{vname} {nov}: no autoplay on open", (audio(b) or {}).get("paused", True) is True)
            if mobile:
                sw = overflow(b)
                check(f"{vname} {nov}: no horizontal overflow", sw[0] <= sw[1], str(sw))

        # ---- full interaction flow on each novel (play, highlight); deep flow on Butterfly
        for nov, (cid, nxt) in CH.items():
            b.goto(f"{BASE}/chapters/{cid}", settle=2.0, wait_expr="document.querySelector('.dock-play')", timeout=240)
            b.click(".dock-play")
            try:
                wait_playing(b)
                check(f"{vname} {nov}: plays after pressing Phát", True)
            except TimeoutError as e:
                check(f"{vname} {nov}: plays after pressing Phát", False, str(e)[:200])
                continue
            time.sleep(1.0)
            check(f"{vname} {nov}: dock expanded while playing", b.eval("!!document.querySelector('.dock:not(.dock-mini)')"))
            hidden = b.eval("""(() => [...document.querySelectorAll('.dock button, .dock select, .dock input')].filter(el => {
                const r = el.getBoundingClientRect(); if (!r.width) return false;
                const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                return !(hit && (hit === el || el.contains(hit)));
              }).map(el => el.getAttribute('aria-label') || el.className))()""")
            check(f"{vname} {nov}: every dock control is clickable (nothing overlaps it)", not hidden, str(hidden))
            inview = b.eval("(() => { const r = document.querySelector('.dock').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight + 1; })()")
            check(f"{vname} {nov}: dock fully inside the viewport", inview)
            b.shot(OUT / f"{vname}_{nov}_02_playing.png")

            click_seek(b, 0.42)
            time.sleep(2.5)
            act = b.eval(ACTIVE)
            check(f"{vname} {nov}: exactly one highlighted paragraph after seek", act and act.get("n") == 1, json.dumps(act))
            check(f"{vname} {nov}: follow mode scrolled highlighted paragraph into view", in_view(act), json.dumps(act))
            b.shot(OUT / f"{vname}_{nov}_03_highlight.png")
            if mobile:
                sw = overflow(b)
                check(f"{vname} {nov}: no horizontal overflow while playing", sw[0] <= sw[1], str(sw))

            if nov != "butterfly":
                b.eval("document.querySelector('audio').pause()")
                continue

            # manual scroll away -> follow suspended, jump chip appears, no snap-back
            b.wheel(w // 2, h // 3, -2600, steps=8)
            time.sleep(4.0)
            act = b.eval(ACTIVE)
            chip = b.eval("(() => { const c = document.querySelector('.reader-chip-main'); return c ? c.textContent : null })()")
            check(f"{vname}: manual scroll suspends follow (no snap-back for 4s)", not in_view(act), json.dumps(act))
            check(f"{vname}: 'Tới đoạn đang đọc' chip shown after manual scroll", bool(chip) and "Tới đoạn đang đọc" in chip, str(chip))
            check(f"{vname}: audio keeps playing while user scrolls", not audio(b)["paused"])
            b.shot(OUT / f"{vname}_{nov}_04_scrolled_away.png")

            b.click(".reader-chip-main")
            time.sleep(1.8)
            act = b.eval(ACTIVE)
            check(f"{vname}: jump-to-current brings paragraph back", in_view(act), json.dumps(act))
            check(f"{vname}: chip hidden once following again", not b.eval("!!document.querySelector('.reader-chip-main')"))
            b.shot(OUT / f"{vname}_{nov}_05_jump_to_current.png")

            # hide text -> listen mode, text closed, audio continues
            t_before = audio(b)["t"]
            ok = click_text(b, ".dock-chip", "Ẩn truyện chữ")
            time.sleep(2.0)
            a = audio(b)
            check(f"{vname}: 'Ẩn truyện chữ' switches to listen with text hidden",
                  ok and b.eval("document.querySelector('.reader').hidden === true && !!document.querySelector('.reader-hero')"))
            check(f"{vname}: hiding text never stops audio", (not a["paused"]) and a["t"] > t_before, f"{t_before:.1f}->{a['t']:.1f}")
            b.shot(OUT / f"{vname}_{nov}_06_text_hidden.png")

            ok = click_text(b, ".reader-closed button, .reader-drawer-ctl button", "Hiện truyện chữ") or \
                click_text(b, ".reader-drawer-ctl button", "Mở")
            time.sleep(1.5)
            a2 = audio(b)
            check(f"{vname}: 'Hiện truyện chữ' restores the text", ok and b.eval("document.querySelector('.reader').hidden === false"))
            check(f"{vname}: restoring text never stops audio", (not a2["paused"]) and a2["t"] > a["t"], f"{a['t']:.1f}->{a2['t']:.1f}")
            b.shot(OUT / f"{vname}_{nov}_07_text_restored.png")

            # back to Doc+Nghe, keyboard controls
            click_text(b, ".reader-mode", "Đọc + Nghe")
            time.sleep(1.0)
            check(f"{vname}: switching Nghe -> Đọc+Nghe keeps audio playing", not audio(b)["paused"])
            b.eval("document.activeElement && document.activeElement.blur()")
            b.key("k", "KeyK", "k", 75)
            time.sleep(0.6)
            check(f"{vname}: K pauses", audio(b)["paused"])
            t0 = audio(b)["t"]
            b.key("j", "KeyJ", "j", 74)
            time.sleep(0.6)
            check(f"{vname}: J seeks back 10s", abs((t0 - audio(b)["t"]) - 10) < 1.5, f"{t0:.1f}->{audio(b)['t']:.1f}")
            b.key("k", "KeyK", "k", 75)
            time.sleep(0.8)
            check(f"{vname}: K resumes", not audio(b)["paused"])

            # next chapter from the dock while playing -> next chapter plays
            old_src = audio(b)["src"]
            b.eval("(() => { const d = document.querySelector('.dock-mini .dock-mini-title'); if (d) d.click(); })()")
            time.sleep(0.5)
            b.click('.dock button[aria-label="Chương sau"]')
            try:
                b.wait(f"location.pathname === '/chapters/{nxt}'", timeout=240)
                b.wait("document.querySelector('.reader-para')", timeout=240)
                wait_playing(b, min_t=0.8, timeout=60)
                a3 = audio(b)
                check(f"{vname}: 'Chương sau' while playing continues with next chapter audio",
                      a3["src"] != old_src and not a3["paused"], a3["src"][:60])
            except TimeoutError as e:
                check(f"{vname}: 'Chương sau' while playing continues with next chapter audio", False, str(e)[:200])
            check(f"{vname}: still one <audio> after navigation", n_audio(b) == 1)
            check(f"{vname}: GlobalMiniPlayer hidden on the playing chapter's page", not b.eval("!!document.querySelector('.mini')"))
            time.sleep(1.5)
            b.shot(OUT / f"{vname}_{nov}_08_next_chapter.png")
            b.eval("document.querySelector('audio').pause()")

            # resume offer on returning to the earlier chapter (full reload = fresh engine)
            b.goto(f"{BASE}/chapters/{cid}", settle=2.5, wait_expr="document.querySelector('.reader-para')", timeout=240)
            banner = b.eval("(() => { const r = document.querySelector('.reader-resume'); return r ? r.textContent : null })()")
            check(f"{vname}: resume offer on return", bool(banner) and "Tiếp tục nghe" in banner, str(banner)[:120])
            check(f"{vname}: no autoplay on return", audio(b)["paused"])
            b.shot(OUT / f"{vname}_{nov}_09_resume_offer.png")
            if banner and "Tiếp tục nghe" in banner:
                click_text(b, ".reader-resume button", "Tiếp tục nghe")
                try:
                    wait_playing(b, min_t=20, timeout=60)
                    check(f"{vname}: 'Tiếp tục nghe' resumes from saved position", audio(b)["t"] > 20, f"t={audio(b)['t']:.1f}")
                except TimeoutError as e:
                    check(f"{vname}: 'Tiếp tục nghe' resumes from saved position", False, str(e)[:160])
                b.eval("document.querySelector('audio').pause()")

        errs = [e for e in b.console_errors() if "405" not in e and "reportListen" not in e]
        check(f"{vname}: no unexpected console errors", not errs, "; ".join(errs)[:400])
    finally:
        b.close()


def run_special():
    """Desktop-only: /listen redirect, listen mode hero, reduced motion, signed-URL refresh."""
    b = Browser()
    try:
        b.viewport(1366, 768)
        cid = CH["genshin"][0]
        # Old link -> server redirect; wait for the FINAL url, not the requested one.
        b.send("Page.navigate", {"url": f"{BASE}/listen/{cid}"})
        b.wait(f"location.pathname === '/chapters/{cid}' && !!document.querySelector('.reader-hero')", timeout=240)
        time.sleep(2.0)
        check("old /listen/[id] lands on /chapters/[id]?mode=listen", b.eval("location.pathname + location.search") == f"/chapters/{cid}?mode=listen")
        check("listen mode shows hero player + collapsed text drawer",
              b.eval("!!document.querySelector('.listen-hero') && !!document.querySelector('.reader-now')"))
        b.shot(OUT / "1366x768_genshin_10_listen_mode.png")

        # (A) REACTIVE refresh: the signed URL starts answering 403 like an expired
        #     R2 link (CDP request interception), mid-playback, and a seek forces a
        #     new range request.
        b.click(".listen-hero .play-btn")
        wait_playing(b, min_t=3)
        old = audio(b)["src"]
        b.send("Fetch.enable", {"patterns": [{"urlPattern": "*r2.cloudflarestorage.com*", "requestStage": "Request"}]})
        click_seek(b, 0.8)
        ok = False
        deadline = time.time() + 60
        served403 = 0
        while time.time() < deadline:
            served403 += fetch_pump(b, 1.0, old)
            a = b.eval(AUDIO)
            if a and a["src"] != old and not a["paused"] and a["t"] > a["d"] * 0.7:
                ok = True
                break
        a = audio(b)
        err = b.eval("(() => { const x = document.querySelector('.alert-error'); return x ? x.textContent : '' })()")
        check("signed URL refresh (reactive): 403 on the old URL -> new URL, position kept, playback resumed",
              ok and served403 > 0, f"403 served={served403} t={a['t']:.1f}/{a['d']:.1f} err={err[:80]}")
        b.send("Fetch.disable")
        b.eval("document.querySelector('audio').pause()")

        # (B) PROACTIVE refresh: paused "for 5 hours" (clock moved forward), then Play
        #     must fetch a fresh URL BEFORE playing, and resume from the same spot.
        before = audio(b)
        b.eval("(() => { const real = Date.now; const off = 5 * 3600 * 1000; Date.now = () => real() + off; })()")
        b.click(".listen-hero .play-btn")
        try:
            b.wait(f"(() => {{ const a = document.querySelector('audio'); return a && a.getAttribute('src') !== {json.dumps(before['src'])} && !a.paused; }})()", timeout=45)
            a = audio(b)
            check("signed URL refresh (proactive): expired while paused -> new URL before play, same position",
                  abs(a["t"] - before["t"]) < 5, f"{before['t']:.1f}->{a['t']:.1f}")
        except TimeoutError as e:
            check("signed URL refresh (proactive): expired while paused -> new URL before play, same position", False, str(e)[:160])
        b.eval("document.querySelector('audio').pause()")
    finally:
        b.close()

    # reduced motion: follow defaults OFF -> no auto-scroll, chip offered instead
    b = Browser()
    try:
        b.viewport(1366, 768)
        b.emulate_media(reduced_motion=True)
        cid = CH["cold"][0]
        b.goto(f"{BASE}/chapters/{cid}", settle=2.0, wait_expr="document.querySelector('.dock-play')", timeout=240)
        b.click(".dock-play")
        wait_playing(b)
        y0 = b.eval("scrollY")
        click_seek(b, 0.6)
        time.sleep(3)
        y1 = b.eval("scrollY")
        act = b.eval(ACTIVE)
        check("reduced motion: no auto-scroll to the spoken paragraph", abs(y1 - y0) < 5, f"scrollY {y0}->{y1}")
        check("reduced motion: highlight still shown + jump chip offered",
              act.get("n") == 1 and b.eval("!!document.querySelector('.reader-chip-main')"), json.dumps(act))
        b.shot(OUT / "1366x768_cold_11_reduced_motion.png")
        b.eval("document.querySelector('audio').pause()")
    finally:
        b.close()


if __name__ == "__main__":
    only = sys.argv[1:] or [v[0] for v in VIEWPORTS] + ["special"]
    for vname, w, h, mobile in VIEWPORTS:
        if vname in only:
            run_viewport(vname, w, h, mobile)
    if "special" in only:
        run_special()
    OUT.mkdir(parents=True, exist_ok=True)
    prev = []
    rp = OUT / "results.json"
    if rp.exists() and sys.argv[1:]:
        prev = [r for r in json.loads(rp.read_text(encoding="utf-8")) if not any(r["check"].startswith(o) for o in only)]
    rp.write_text(json.dumps(prev + RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
    fails = [r for r in RESULTS if not r["ok"]]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} checks passed")
