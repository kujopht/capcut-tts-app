"""Smoke: menu -> intro -> man choi; chup anh; kiem loi console."""
import json
import time

from qa_common import *  # noqa: F401,F403

b = new_browser(1280, 720)
try:
    b.goto(URL, settle=1.5, wait_expr="document.querySelector('.isc-menu')")
    shot(b, "01_menu.png")
    print("title:", b.eval("document.title"))
    print("cards:", b.eval("document.querySelectorAll('.card').length"))
    start_game(b, settle=2.0)
    shot(b, "02_stage.png")
    print("state:", json.dumps(b.eval(api("({room: g.roomId, x: g.player.x, y: g.player.y, hp: g.player.hp, mode: g.mode, frame: g.frame})"))))
    print("stats:", json.dumps(b.eval("window.__INK_QA_API__.runtime.stats()")))
    print("console errors:", b.console_errors())
finally:
    b.close()
