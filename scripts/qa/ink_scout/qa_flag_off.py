"""Cờ TẮT (build mặc định): thẻ không hiện ở Giải trí, route chỉ là thông báo, không chunk game nào được tải."""
import json
import time

from qa_common import *  # noqa: F401,F403

res = {}
b = new_browser(1280, 720, qa=False)
try:
    b.send("Network.setCacheDisabled", {"cacheDisabled": True})
    b.goto(BASE + "/entertainment", settle=2.0)
    res["entertainment_has_card"] = b.eval("document.body.innerText.includes('Ink Scout: The Lost Chapter')")
    res["entertainment_has_link"] = b.eval("!!document.querySelector('a[href=\"/entertainment/ink-scout\"]')")
    b.events.clear()
    b.goto(BASE + "/entertainment/ink-scout", settle=2.0)
    for _ in range(3):
        b.eval("1"); time.sleep(0.2)
    scripts = [m["params"]["response"]["url"] for m in b.events if m.get("method") == "Network.responseReceived" and m["params"].get("type") == "Script"]
    res["route_text"] = b.eval("document.querySelector('.page') ? document.querySelector('.page').innerText.slice(0, 120) : document.body.innerText.slice(0, 120)")
    res["route_has_menu"] = b.eval("!!document.querySelector('.isc-menu')")
    res["route_has_canvas"] = b.eval("!!document.querySelector('canvas')")
    res["scripts_loaded"] = len(scripts)
    game_hits = 0
    for m in b.events:
        if m.get("method") == "Network.responseReceived" and m["params"].get("type") == "Script":
            try:
                body = b.send("Network.getResponseBody", {"requestId": m["params"]["requestId"]}).get("body", "")
            except Exception:  # noqa: BLE001
                continue
            if "revisionSlash" in body or "lostchapter" in body or "THE REDACTOR" in body:
                game_hits += 1
    res["chunks_with_game_code"] = game_hits
    res["robots_meta"] = b.eval("(document.querySelector('meta[name=robots]') || {}).content")
    print(json.dumps(res, ensure_ascii=False, indent=1))
finally:
    b.close()
