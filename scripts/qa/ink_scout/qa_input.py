"""Kiem tra duong ban phim THAT qua CDP: di, nhay, chem, tam dung (Esc), tiep tuc; va chan cuon trang."""
import json
import time

from qa_common import *  # noqa: F401,F403


def kd(b, key, code, kc):
    b.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": key, "code": code, "windowsVirtualKeyCode": kc, "nativeVirtualKeyCode": kc})


def ku(b, key, code, kc):
    b.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": code, "windowsVirtualKeyCode": kc, "nativeVirtualKeyCode": kc})


def st(b):
    return b.eval(api("({x: Math.round(g.player.x), y: Math.round(g.player.y), vy: +g.player.vy.toFixed(2), onGround: g.player.onGround, atk: g.player.attackKind, ink: g.player.ink, mode: g.mode, paused: A.runtime.stats().frames > 0})"))


b = new_browser(1280, 720)
try:
    start_game(b, settle=1.0)
    b.eval("window.scrollTo(0, 0)")
    s0 = st(b)
    print("start", s0)
    # đi phải 1 giây
    kd(b, "ArrowRight", "ArrowRight", 39)
    time.sleep(1.0)
    ku(b, "ArrowRight", "ArrowRight", 39)
    time.sleep(0.3)
    s1 = st(b)
    print("after right 1s", s1, "dx=", s1["x"] - s0["x"])
    # nhảy (Space) — kiểm tra cuộn trang không đổi
    sy0 = b.eval("window.scrollY")
    kd(b, " ", "Space", 32)
    time.sleep(0.25)
    sj = st(b)
    ku(b, " ", "Space", 32)
    print("jump mid-air", sj)
    time.sleep(0.8)
    print("scrollY before/after:", sy0, b.eval("window.scrollY"))
    # chém (J)
    kd(b, "j", "KeyJ", 74)
    time.sleep(0.06)
    sa = st(b)
    ku(b, "j", "KeyJ", 74)
    print("attack", sa)
    time.sleep(0.5)
    # tạm dừng bằng Esc
    f0 = b.eval(api("g.frame"))
    kd(b, "Escape", "Escape", 27)
    ku(b, "Escape", "Escape", 27)
    time.sleep(0.6)
    f1 = b.eval(api("g.frame"))
    time.sleep(0.6)
    f2 = b.eval(api("g.frame"))
    print("pause: frame", f0, f1, f2, "-> frozen:", f1 == f2, "overlay:", b.eval("!!document.querySelector('.isc-pause')"))
    shot(b, "03_paused.png")
    # tiếp tục bằng nút
    click_text(b, "Tiếp tục")
    time.sleep(0.5)
    f3 = b.eval(api("g.frame"))
    time.sleep(0.5)
    f4 = b.eval(api("g.frame"))
    print("resumed running:", f4 > f3)
    # mất tiêu điểm / ẩn tab -> tạm dừng
    print("console errors:", b.console_errors())
finally:
    b.close()
