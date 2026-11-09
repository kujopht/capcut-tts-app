"""QA di dong: 320/360/390/430 (doc) + ngang; cham that qua CDP; do bo cuc, trung lap HUD, cuon trang, nhieu ngon, xoay man hinh."""
import json
import sys
import time

from qa_common import *  # noqa: F401,F403

VIEWPORTS = [(320, 568), (360, 740), (390, 844), (430, 932), (568, 320), (740, 360), (844, 390), (932, 430)]
if len(sys.argv) > 1:
    VIEWPORTS = [tuple(int(x) for x in a.split("x")) for a in sys.argv[1:]]


def touch(b, typ, pts):
    b.send("Input.dispatchTouchEvent", {"type": typ, "touchPoints": [{"x": x, "y": y, "id": i, "radiusX": 12, "radiusY": 12, "force": 1} for (x, y, i) in pts]})


def rect(b, sel):
    return b.eval(f"""(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return {{x:r.x,y:r.y,w:r.width,h:r.height}}; }})()""")


def center(r):
    return (r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)


def inter(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def st(b):
    return b.eval(api("({x: +g.player.x.toFixed(1), y: +g.player.y.toFixed(1), vx: +g.player.vx.toFixed(2), onGround: g.player.onGround, atk: g.player.attackKind, ink: g.player.ink, pulseT: g.player.pulseT, frame: g.frame})"))


results = []
for (w, h) in VIEWPORTS:
    name = f"{w}x{h}"
    b = new_browser(w, h, mobile=True)
    r = {"viewport": name, "checks": {}}
    try:
        start_game(b, settle=0.8)
        time.sleep(0.5)
        r["coarse"] = b.eval("matchMedia('(pointer: coarse)').matches")
        r["touch_controls"] = b.eval("!!document.querySelector('.isc-touch')")
        cv = rect(b, ".isc-view")
        r["canvas_css"] = [round(cv["x"]), round(cv["y"]), round(cv["w"]), round(cv["h"])]
        r["canvas_scale"] = round(cv["w"] / 384, 3)
        # không cuộn ngang; trang bị khoá cuộn
        r["checks"]["no_h_scroll"] = b.eval("document.documentElement.scrollWidth <= window.innerWidth + 1")
        r["checks"]["scroll_locked"] = b.eval("getComputedStyle(document.body).overflow === 'hidden' && getComputedStyle(document.documentElement).overflow === 'hidden'")
        # kích thước nút
        sizes = {}
        for k, sel in {"pad": ".isc-pad", "jump": ".isc-tb-jump", "attack": ".isc-tb-attack", "pulse": ".isc-tb-pulse", "pause": ".isc-tb-pause"}.items():
            rr = rect(b, sel)
            sizes[k] = None if rr is None else [round(rr["w"]), round(rr["h"])]
        r["button_sizes"] = sizes
        r["checks"]["main_buttons_ge_56"] = all(sizes[k] and min(sizes[k]) >= 56 for k in ("jump", "attack", "pulse"))
        r["checks"]["pause_ge_44"] = bool(sizes["pause"] and min(sizes["pause"]) >= 44)
        # trùng lặp với HUD (góc trên trái) và thanh boss (đáy giữa) — vùng nội bộ -> px CSS
        sc = cv["w"] / 384
        hud = {"x": cv["x"], "y": cv["y"], "w": 150 * sc, "h": 40 * sc}
        bossbar = {"x": cv["x"] + 107 * sc, "y": cv["y"] + 198 * sc, "w": 170 * sc, "h": 14 * sc}
        overlaps = []
        for k, sel in {"pad": ".isc-pad", "jump": ".isc-tb-jump", "attack": ".isc-tb-attack", "pulse": ".isc-tb-pulse", "pause": ".isc-tb-pause"}.items():
            rr = rect(b, sel)
            if rr and inter(rr, hud):
                overlaps.append(f"{k}-HUD")
            if rr and inter(rr, bossbar):
                overlaps.append(f"{k}-bossbar")
        r["overlaps"] = overlaps
        r["checks"]["no_hud_overlap"] = not overlaps
        # điều khiển bằng chạm thật
        pad = rect(b, ".isc-pad")
        s0 = st(b)
        cx, cy = center(pad)
        touch(b, "touchStart", [(cx + pad["w"] * 0.32, cy, 1)])
        time.sleep(0.8)
        s1 = st(b)
        # trượt sang trái mà không nhấc ngón
        touch(b, "touchMove", [(cx - pad["w"] * 0.32, cy, 1)])
        time.sleep(0.9)
        s2 = st(b)
        touch(b, "touchEnd", [])
        time.sleep(0.4)
        r["checks"]["pad_right_moves"] = s1["x"] - s0["x"] > 25
        r["checks"]["pad_slide_left_reverses"] = s2["x"] < s1["x"] - 15
        # nhảy bằng nút
        jb = rect(b, ".isc-tb-jump")
        y0 = st(b)["y"]
        touch(b, "touchStart", [center(jb) + (2,)])
        time.sleep(0.25)
        y1 = st(b)["y"]
        touch(b, "touchEnd", [])
        time.sleep(0.8)
        r["checks"]["jump_button"] = y1 < y0 - 12
        # nhiều ngón: giữ pad phải + chạm chém cùng lúc
        ab = rect(b, ".isc-tb-attack")
        xs = st(b)["x"]
        touch(b, "touchStart", [(cx + pad["w"] * 0.32, cy, 1)])
        touch(b, "touchStart", [(cx + pad["w"] * 0.32, cy, 1), (center(ab)[0], center(ab)[1], 2)])
        time.sleep(0.12)
        sm = st(b)
        time.sleep(0.5)
        sm2 = st(b)
        touch(b, "touchEnd", [])
        r["checks"]["multitouch_move_and_attack"] = sm["atk"] != "none" and sm2["x"] > xs + 10
        # Pulse không đủ Ink: không crash; tạm dừng bằng nút chạm
        pb = rect(b, ".isc-tb-pause")
        touch(b, "touchStart", [center(pb) + (4,)])
        time.sleep(0.08)
        touch(b, "touchEnd", [])
        time.sleep(0.5)
        r["checks"]["pause_by_touch"] = b.eval("!!document.querySelector('.isc-pause')")
        f_a = b.eval(api("g.frame"))
        time.sleep(0.4)
        r["checks"]["paused_frozen"] = f_a == b.eval(api("g.frame"))
        shot(b, f"mobile_{name}_paused.png")
        # Resume: nút "Tiếp tục" đủ lớn để chạm
        rb = b.eval("""(() => { const e = [...document.querySelectorAll('.isc-pause button')].find(x => x.textContent.includes('Tiếp tục')); const r = e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })()""")
        r["checks"]["resume_btn_ge_44"] = min(rb["w"], rb["h"]) >= 44
        touch(b, "touchStart", [center(rb) + (5,)])
        time.sleep(0.08)
        touch(b, "touchEnd", [])
        time.sleep(0.5)
        r["checks"]["resumed"] = not b.eval("!!document.querySelector('.isc-pause')")
        shot(b, f"mobile_{name}.png")
        # cuộn trang khi giữ nút: chạm kéo dọc trên canvas không làm cuộn
        sy = b.eval("window.scrollY")
        touch(b, "touchStart", [(cv["x"] + cv["w"] / 2, cv["y"] + cv["h"] / 2, 3)])
        touch(b, "touchMove", [(cv["x"] + cv["w"] / 2, cv["y"] + cv["h"] / 2 - 120, 3)])
        touch(b, "touchEnd", [])
        r["checks"]["no_page_scroll_on_drag"] = b.eval("window.scrollY") == sy
        # Xoay màn hình: đổi kích thước → bố cục tính lại, game vẫn chạy
        b.viewport(h, w, mobile=True)
        time.sleep(0.8)
        cv2 = rect(b, ".isc-view")
        r["rotated_canvas_css"] = [round(cv2["x"]), round(cv2["y"]), round(cv2["w"]), round(cv2["h"])]
        f1 = b.eval(api("g.frame"))
        time.sleep(0.4)
        r["checks"]["rotate_relayout_and_running"] = (cv2["w"] != cv["w"] or cv2["h"] != cv["h"]) and b.eval(api("g.frame")) > f1 and b.eval("document.documentElement.scrollWidth <= window.innerWidth + 1")
        shot(b, f"mobile_{name}_rotated.png")
        r["console_errors"] = b.console_errors()
        r["pass"] = all(r["checks"].values()) and not r["console_errors"]
    except Exception as e:  # noqa: BLE001
        r["error"] = f"{type(e).__name__}: {e}"
        r["pass"] = False
    finally:
        b.close()
    results.append(r)
    print(json.dumps({k: v for k, v in r.items()}, ensure_ascii=False))

(OUT / "mobile_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
print("TONG:", sum(1 for r in results if r.get("pass")), "/", len(results), "viewport dat")
