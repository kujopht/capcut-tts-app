"""Chan doan chi tiet: listener nao tang them sau lan vao/ra dau; xu huong heap qua 40 vong; thoi gian khoi tao chinh xac; CPU nen khi chua tung choi."""
import json
import time

from qa_common import *  # noqa: F401,F403
from qa_lifecycle_lib import TRACK  # noqa: F401

b = new_browser(1280, 720)
out = {}
try:
    b.send("Page.addScriptToEvaluateOnNewDocument", {"source": TRACK})
    b.send("Page.addScriptToEvaluateOnNewDocument", {"source": r"""
      document.addEventListener('click', () => { window.__tClick = performance.now(); }, true);
      let _v; Object.defineProperty(window, '__INK_QA_API__', { configurable: true, set(v) { window.__tInit = performance.now() - (window.__tClick || 0); _v = v; }, get() { return _v; } });
    """})
    b.send("Performance.enable")
    b.send("HeapProfiler.enable")
    b.goto(URL, settle=1.5, wait_expr="document.querySelector('.isc-menu')")

    def metrics():
        return {x["name"]: x["value"] for x in b.send("Performance.getMetrics")["metrics"]}

    # CPU nền khi CHƯA từng chơi
    m0 = metrics(); time.sleep(3); m1 = metrics()
    out["idle_menu_before_ever_playing"] = {"script_ms_per_s": round((m1["ScriptDuration"] - m0["ScriptDuration"]) / 3 * 1000, 2), "task_ms_per_s": round((m1["TaskDuration"] - m0["TaskDuration"]) / 3 * 1000, 2)}
    base = b.eval("window.__trk()")

    def enter():
        click_text(b, "▶ Chơi") or click_text(b, "▶ Tiếp tục")
        time.sleep(0.25)
        for _ in range(4):
            if b.eval("!!document.querySelector('.isc-intro')"):
                click_text(b, "Xuống Kho") or click_text(b, "Tiếp →")
                time.sleep(0.2)
        b.wait("window.__INK_QA_API__ && window.__INK_QA_API__.game && window.__INK_QA_API__.game.frame > 3", timeout=30)
        return round(b.eval("window.__tInit"), 1)

    def leave():
        if not b.eval("!!document.querySelector('.isc-pause')"):
            b.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            b.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            time.sleep(0.2)
        click_text(b, "Thoát về menu")
        b.wait("document.querySelector('.isc-menu')", timeout=10)

    inits = [enter()]
    time.sleep(0.5)
    leave()
    time.sleep(0.3)
    after1 = b.eval("window.__trk()")
    diff = {k: after1["byType"].get(k, 0) - base["byType"].get(k, 0) for k in set(after1["byType"]) | set(base["byType"]) if after1["byType"].get(k, 0) != base["byType"].get(k, 0)}
    out["listener_diff_after_first_cycle"] = diff

    heaps = []
    for i in range(12):
        inits.append(enter())
        time.sleep(0.15)
        leave()
        b.send("HeapProfiler.collectGarbage")
        heaps.append(round(metrics()["JSHeapUsedSize"] / 1048576, 3))
    out["init_ms_click_to_first_frames"] = {"first": inits[0], "warm_median": sorted(inits[1:])[len(inits[1:]) // 2], "warm_max": max(inits[1:]), "all": inits}
    out["heap_MB_over_40_cycles"] = heaps
    out["heap_slope_MB_per_cycle"] = round((heaps[-1] - heaps[3]) / 8, 4)
    after = b.eval("window.__trk()")
    out["listeners_final_vs_after_first"] = [after["listeners"], after1["listeners"]]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (OUT / "leak2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
finally:
    b.close()
