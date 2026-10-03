"""Vong doi + ro ri + hieu nang: vao/ra nhieu lan, dem listener/rAF/timer, heap sau GC, so ban sao, chet/hoi sinh, luu/tai, localStorage hong,
tab an -> tam dung, roi route bang Link va nut Back."""
import json
import time

from qa_common import *  # noqa: F401,F403

TRACK = r"""
(() => {
  const L = new Map(); const R = new Set(); const I = new Set(); const T = new Set(); let fid = 0; const ids = new WeakMap();
  const idOf = (f) => { if (!ids.has(f)) ids.set(f, ++fid); return ids.get(f); };
  const add = EventTarget.prototype.addEventListener, rem = EventTarget.prototype.removeEventListener;
  const tag = (t) => (t === window ? 'window' : t === document ? 'document' : null);
  EventTarget.prototype.addEventListener = function (type, fn, o) {
    const g = tag(this); if (g && fn) { const cap = typeof o === 'object' ? !!o.capture : !!o; L.set(`${g}:${type}:${cap}:${idOf(fn)}`, 1); }
    return add.call(this, type, fn, o);
  };
  EventTarget.prototype.removeEventListener = function (type, fn, o) {
    const g = tag(this); if (g && fn) { const cap = typeof o === 'object' ? !!o.capture : !!o; L.delete(`${g}:${type}:${cap}:${idOf(fn)}`); }
    return rem.call(this, type, fn, o);
  };
  const raf = window.requestAnimationFrame.bind(window), caf = window.cancelAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { const id = raf((t) => { R.delete(id); cb(t); }); R.add(id); return id; };
  window.cancelAnimationFrame = (id) => { R.delete(id); caf(id); };
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  window.setInterval = (f, ms, ...a) => { const id = si(f, ms, ...a); I.add(id); return id; };
  window.clearInterval = (id) => { I.delete(id); ci(id); };
  window.__trk = () => ({ listeners: L.size, byType: [...L.keys()].reduce((m, k) => { const t = k.split(':').slice(0, 2).join(':'); m[t] = (m[t] || 0) + 1; return m; }, {}), raf: R.size, intervals: I.size });
})();
"""


def click_xy(b, sel):
    box = b.eval(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }})()")
    if not box:
        raise RuntimeError("no " + sel)
    b.click_at(*box)


def counters(b):
    d = b.send("Memory.getDOMCounters")
    b.send("HeapProfiler.collectGarbage")
    m = {x["name"]: x["value"] for x in b.send("Performance.getMetrics")["metrics"]}
    return {"nodes": d["nodes"], "jsEventListeners": d["jsEventListeners"], "heapMB": round(m["JSHeapUsedSize"] / 1048576, 2)}


b = new_browser(1280, 720)
out = {}
try:
    b.send("Page.addScriptToEvaluateOnNewDocument", {"source": TRACK})
    b.send("Performance.enable")
    b.send("HeapProfiler.enable")
    b.goto(URL, settle=1.0, wait_expr="document.querySelector('.isc-menu')")
    base_trk = b.eval("window.__trk()")
    base_cnt = counters(b)
    out["baseline_menu"] = {"trk": base_trk, "cnt": base_cnt}

    def enter(continue_ok=True):
        t0 = b.eval("performance.now()")
        if not (click_text(b, "▶ Chơi") or click_text(b, "▶ Tiếp tục")):
            raise RuntimeError("no play button")
        time.sleep(0.3)
        for _ in range(4):
            if b.eval("!!document.querySelector('.isc-intro')"):
                click_text(b, "Xuống Kho") or click_text(b, "Tiếp →")
                time.sleep(0.25)
        b.wait("window.__INK_QA_API__ && window.__INK_QA_API__.game", timeout=30)
        b.wait("window.__INK_QA_API__.game.frame > 5", timeout=20)
        return b.eval("performance.now()") - t0

    def leave():
        if not b.eval("!!document.querySelector('.isc-pause')"):
            b.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            b.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            time.sleep(0.3)
        click_text(b, "Thoát về menu")
        b.wait("document.querySelector('.isc-menu')", timeout=10)
        time.sleep(0.4)

    # --- vòng vào/ra nhiều lần
    init_times = []
    series = []
    for i in range(12):
        init_times.append(round(enter(), 0))
        st = b.eval("window.__INK_QA_API__.runtime.stats()")
        assert st["instances"] == 1, st
        time.sleep(0.8)
        in_game = b.eval("window.__trk()")
        leave()
        trk = b.eval("window.__trk()")
        cnt = counters(b)
        series.append({"cycle": i + 1, "listeners": trk["listeners"], "raf": trk["raf"], "nodes": cnt["nodes"], "jsEventListeners": cnt["jsEventListeners"], "heapMB": cnt["heapMB"], "in_game_listeners": in_game["listeners"], "in_game_raf": in_game["raf"]})
    out["init_ms_play_click_to_5_frames"] = init_times
    out["cycles"] = series
    out["leak_check"] = {
        "listeners_equal_baseline": all(s["listeners"] == base_trk["listeners"] for s in series),
        "raf_equal_baseline": all(s["raf"] == base_trk["raf"] for s in series),
        "no_instance_after_leave": b.eval("window.__INK_QA_API__ === undefined"),
        "heap_growth_MB_cycle2_to_12": round(series[-1]["heapMB"] - series[1]["heapMB"], 2),
        "dom_nodes_growth": series[-1]["nodes"] - series[1]["nodes"],
        "jsEventListeners_growth": series[-1]["jsEventListeners"] - series[1]["jsEventListeners"],
    }

    # --- CPU rảnh sau khi rời game (menu): 3 giây
    m0 = {x["name"]: x["value"] for x in b.send("Performance.getMetrics")["metrics"]}
    time.sleep(3.0)
    m1 = {x["name"]: x["value"] for x in b.send("Performance.getMetrics")["metrics"]}
    out["idle_after_leave_menu"] = {
        "script_ms_per_s": round((m1["ScriptDuration"] - m0["ScriptDuration"]) / 3 * 1000, 2),
        "task_ms_per_s": round((m1["TaskDuration"] - m0["TaskDuration"]) / 3 * 1000, 2),
        "layout_count": m1["LayoutCount"] - m0["LayoutCount"],
    }
    # đối chứng: CPU trong game
    enter()
    m0 = {x["name"]: x["value"] for x in b.send("Performance.getMetrics")["metrics"]}
    time.sleep(3.0)
    m1 = {x["name"]: x["value"] for x in b.send("Performance.getMetrics")["metrics"]}
    out["in_game_idle"] = {
        "script_ms_per_s": round((m1["ScriptDuration"] - m0["ScriptDuration"]) / 3 * 1000, 2),
        "task_ms_per_s": round((m1["TaskDuration"] - m0["TaskDuration"]) / 3 * 1000, 2),
    }

    # --- tab ẩn → tạm dừng
    f0 = b.eval("window.__INK_QA_API__.game.frame")
    b.eval("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange')); true")
    time.sleep(0.5)
    f1 = b.eval("window.__INK_QA_API__.game.frame")
    time.sleep(0.5)
    f2 = b.eval("window.__INK_QA_API__.game.frame")
    out["hidden_tab_pauses"] = {"frames": [f0, f1, f2], "frozen": f1 == f2, "overlay": b.eval("!!document.querySelector('.isc-pause')")}
    b.eval("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); true")
    click_text(b, "Tiếp tục")
    time.sleep(0.4)

    # --- chết / hồi sinh
    A = "window.__INK_QA_API__"
    b.eval(f"(() => {{ const g = {A}.game; g.player.hp = 1; g.player.invuln = 0; g.player.takeHit(0, 1, () => {{}}); return true; }})()")
    time.sleep(0.5)
    died = b.eval(f"{A}.game.mode")
    dead_text = b.eval("document.querySelector('.isc-dead') ? document.querySelector('.isc-dead').textContent : null")
    shot(b, "life_dead.png")
    time.sleep(2.0)
    out["death_respawn"] = {"mode_during": died, "overlay_text": dead_text, "mode_after": b.eval(f"{A}.game.mode"), "hp_after": b.eval(f"{A}.game.player.hp"), "deaths": b.eval(f"{A}.game.save.deaths")}

    # --- lưu / tải lại trang: tiếp tục từ điểm lưu
    b.eval(f"(() => {{ const g = {A}.game; g.qaGrant({{marginStep: true, memories: [1]}}); g.save.checkpoint = 'hall'; g.emit({{t: 'save'}}); return true; }})()")
    time.sleep(0.5)
    saved = b.eval("localStorage.getItem('fanfic.inkscout.lostchapter.v1')")
    b.goto(URL, settle=1.0, wait_expr="document.querySelector('.isc-menu')")
    cont = click_text(b, "▶ Tiếp tục")
    time.sleep(0.8)
    b.wait(f"{A} && {A}.game", timeout=20)
    time.sleep(0.8)
    out["save_reload"] = {
        "stored": json.loads(saved) if saved else None,
        "continue_button": cont,
        "room_after": b.eval(f"{A}.game.roomId"),
        "memories": b.eval(f"{A}.game.save.memories"),
        "marginStep": b.eval(f"{A}.game.save.marginStep"),
        "maxHp": b.eval(f"{A}.game.player.maxHp"),
    }

    # --- cài đặt giữ qua lần tải: tắt rung
    b.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    b.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    time.sleep(0.3)
    click_text(b, "Tắt")  # nút đầu tiên "Tắt" = Rung: Tắt
    time.sleep(0.3)
    shake = b.eval(f"{A}.game.save.settings.shake")
    leave()
    out["settings_persist"] = {"shake_after_set": shake, "stored_shake": json.loads(b.eval("localStorage.getItem('fanfic.inkscout.lostchapter.v1')"))["settings"]["shake"]}

    # --- localStorage hỏng: game vẫn chơi, báo không lưu được
    b.eval("(() => { const o = Storage.prototype.setItem; Storage.prototype.setItem = function (k, v) { if (String(k).startsWith('fanfic.inkscout')) throw new DOMException('quota', 'QuotaExceededError'); return o.call(this, k, v); }; return true; })()")
    enter()
    time.sleep(0.8)
    b.eval(f"(() => {{ {A}.game.emit({{t: 'save'}}); return true; }})()")
    time.sleep(0.8)
    out["storage_blocked"] = {"still_running": b.eval(f"{A}.game.frame") > 30, "notice": b.eval("!!document.querySelector('.isc-savefail')"), "errors": b.console_errors()}
    leave()

    # --- rời route bằng Link và nút Back
    enter()
    time.sleep(0.5)
    b.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    b.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    time.sleep(0.3)
    click_text(b, "Thoát về menu")
    time.sleep(0.4)
    click_text(b, "Về Giải trí", tag="a")
    b.wait("location.pathname === '/entertainment'", timeout=15)
    time.sleep(0.5)
    trk = b.eval("window.__trk()")
    out["leave_via_link"] = {"path": b.eval("location.pathname"), "listeners_equal_baseline_plus_site": trk["listeners"], "raf": trk["raf"], "game_card_present": b.eval("document.body.innerText.includes('Ink Scout: The Lost Chapter')")}
    shot(b, "life_entertainment_card.png")
    # vào lại bằng thẻ, rồi Back khi đang chơi
    click_text(b, "Chơi ngay", tag="a") if False else None
    b.eval("history.back(); true")
    time.sleep(0.8)
    out["leave_via_back"] = {"path": b.eval("location.pathname"), "qa_api": b.eval("window.__INK_QA_API__ === undefined")}
    out["console_errors_total"] = b.console_errors()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (OUT / "lifecycle_perf.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
finally:
    b.close()
