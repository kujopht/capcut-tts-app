"""Choi THAT toan chuong trong Chrome (vong lap + canvas + DOM that), dieu khien bang bot cham phan ung 15 khung.

Doc lap voi mo phong headless: o day vong lap rAF, dong ho, input controller, renderer, overlay React deu chay that.
Ghi: nhat ky trang thai moi giay, anh chup tai cac cot moc, thong ke khung hinh, loi console.
Tham so: argv[1]=ending (restore|erase), argv[2]=goals (full|min), argv[3]=reaction.
"""
import json
import statistics
import sys
import time

from qa_common import *  # noqa: F401,F403

ending = sys.argv[1] if len(sys.argv) > 1 else "restore"
goals = sys.argv[2] if len(sys.argv) > 2 else "full"
reaction = int(sys.argv[3]) if len(sys.argv) > 3 else 15
tag = f"{goals}_{ending}_{reaction}"

bundle = (OUT / "bot_bundle.js").read_text(encoding="utf-8")
b = new_browser(1280, 720)
log = []
shots = []
try:
    start_game(b, settle=0.5)
    b.eval(bundle)
    b.eval(
        f"""(() => {{
          const A = window.__INK_QA_API__, B = window.__INK_BOT__;
          window.__bot = B.createBot(B.core, A.game, {{ goals: {'B.FULL_GOALS' if goals == 'full' else 'B.MIN_GOALS'}, ending: {json.dumps(ending)}, reaction: {reaction} }});
          A.runtime.input.controller = () => window.__bot.next();
          window.__ft = []; let last = performance.now();
          (function loop() {{ requestAnimationFrame((t) => {{ window.__ft.push(t - last); last = t; if (window.__ft.length < 200000) loop(); }}); }})();
          return true;
        }})()"""
    )
    t0 = time.time()
    seen_rooms = set()
    last_mem = 0
    last_phase = 1
    last_mode = ""
    done = False
    while time.time() - t0 < 600:
        s = b.eval(api("""({room: g.roomId, mode: g.mode, hp: g.player.hp, ink: g.player.ink, mem: g.save.memories.length, step: g.save.marginStep,
            boss: g.boss ? {st: g.boss.state, hp: g.boss.hp, ph: g.boss.phase, at: g.boss.attack} : null, frames: g.save.playFrames, deaths: g.save.deaths,
            defeated: g.save.bossDefeated, ending: g.save.ending, goal: window.__bot.goalIndex})"""))
        s["real"] = round(time.time() - t0, 1)
        log.append(s)
        want_shot = None
        if s["room"] not in seen_rooms:
            seen_rooms.add(s["room"])
            want_shot = f"room_{s['room']}"
        if s["mem"] != last_mem:
            last_mem = s["mem"]
            want_shot = f"memory_{s['mem']}"
        if s["boss"] and s["boss"]["ph"] != last_phase:
            last_phase = s["boss"]["ph"]
            want_shot = f"boss_phase{last_phase}"
        if s["mode"] != last_mode:
            last_mode = s["mode"]
            if s["mode"] in ("read", "ending", "complete"):
                want_shot = f"mode_{s['mode']}_{s['frames']}"
        if want_shot:
            time.sleep(0.15)
            shot(b, f"pt_{tag}_{want_shot}.png")
            shots.append(want_shot)
        if s["mode"] == "complete":
            done = True
            break
        time.sleep(1.0)
    time.sleep(0.5)
    shot(b, f"pt_{tag}_final.png")
    ft = b.eval("window.__ft.slice(5)")
    st = sorted(ft)
    n = len(st)
    summary = {
        "done": done,
        "real_seconds": round(time.time() - t0, 1),
        "play_frames": log[-1]["frames"],
        "play_seconds": round(log[-1]["frames"] / 60, 1),
        "deaths": log[-1]["deaths"],
        "memories": log[-1]["mem"],
        "ending": log[-1]["ending"],
        "frame_ms_mean": round(statistics.mean(ft), 2),
        "frame_ms_p95": round(st[int(n * 0.95)], 2),
        "frame_ms_p99": round(st[int(n * 0.99)], 2),
        "frame_ms_max": round(st[-1], 2),
        "frames_over_33ms": sum(1 for x in ft if x > 33.4),
        "frames_total": n,
        "runtime_stats": b.eval("window.__INK_QA_API__.runtime.stats()"),
        "bot_stats": b.eval("window.__bot.stats"),
        "console_errors": b.console_errors(),
        "shots": shots,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    (OUT / f"pt_{tag}_log.json").write_text(json.dumps({"summary": summary, "log": log}, ensure_ascii=False), encoding="utf-8")
finally:
    b.close()
