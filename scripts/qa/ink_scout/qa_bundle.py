"""Do goi JS theo trang (mang that, cache lanh): trang chu, Giai tri, route game, va phan tai THEM khi bam Choi. Tim chunk chua ma game."""
import json
import re
import time

from qa_common import *  # noqa: F401,F403

MARKERS = {"runtime": ["revisionSlash", "Canvas 2D"], "lore/ui": ["THE REDACTOR", "Ký Ức I", "fanfic.inkscout"], "any": ["inkscout", "lostchapter"]}


def collect(b, since=0):
    for _ in range(3):
        b.eval("1")
        time.sleep(0.2)
    reqs = {}
    for m in b.events:
        method = m.get("method")
        p = m.get("params", {})
        if method == "Network.responseReceived" and p.get("type") in ("Script", "Stylesheet"):
            reqs[p["requestId"]] = {"url": p["response"]["url"], "type": p["type"], "size": 0, "status": p["response"]["status"]}
        elif method == "Network.loadingFinished" and p["requestId"] in reqs:
            reqs[p["requestId"]]["size"] = p["encodedDataLength"]
    out = []
    for rid, r in reqs.items():
        body = ""
        try:
            res = b.send("Network.getResponseBody", {"requestId": rid})
            body = res.get("body", "")
        except Exception:  # noqa: BLE001
            pass
        r["flags"] = [k for k, ms in MARKERS.items() if any(x in body for x in ms)]
        r["raw"] = len(body)
        r["url"] = re.sub(r"^http://[^/]+", "", r["url"])
        out.append(r)
    return out


def total(rs, typ="Script"):
    return sum(r["size"] for r in rs if r["type"] == typ)


res = {}
for path in ["/", "/entertainment", "/entertainment/ink-scout"]:
    b = new_browser(1280, 720, qa=False)
    try:
        b.send("Network.setCacheDisabled", {"cacheDisabled": True})
        b.events.clear()
        b.goto(BASE + path, settle=2.5)
        rs = collect(b)
        res[path] = {"js_transfer_bytes": total(rs), "css_transfer_bytes": total(rs, "Stylesheet"), "scripts": len(rs), "game_chunks": [r for r in rs if r["flags"]]}
        if path == "/entertainment/ink-scout":
            b.eval("1")
            b.events.clear()
            click_text(b, "▶ Chơi")
            time.sleep(0.4)
            for _ in range(3):
                if b.eval("!!document.querySelector('.isc-intro')"):
                    click_text(b, "Xuống Kho") or click_text(b, "Tiếp →")
                    time.sleep(0.3)
            b.wait("!!document.querySelector('.isc-canvas')", timeout=20)
            time.sleep(2.0)
            rs2 = collect(b)
            res["after_play_extra"] = {"js_transfer_bytes": total(rs2), "scripts": [{"url": r["url"], "transfer": r["size"], "raw": r["raw"], "flags": r["flags"]} for r in rs2]}
    finally:
        b.close()

print(json.dumps(res, ensure_ascii=False, indent=1))
(OUT / "bundle.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
