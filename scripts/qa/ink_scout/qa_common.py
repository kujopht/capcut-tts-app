"""Tiện ích QA cho Ink Scout: khởi động Chrome headless qua CDP, điều hướng, bấm nút theo chữ, chụp ảnh.

Cần: `pip install websocket-client`, Chrome (đặt CHROME nếu không ở đường dẫn mặc định), và web đã build với cờ bật rồi chạy `next start`:
    set NEXT_PUBLIC_GAME_INK_SCOUT_ENABLED=1 && npm --prefix web run build && npm --prefix web run start -- -p 3100
Biến môi trường: INK_QA_BASE (mặc định http://127.0.0.1:3100). Ảnh/JSON ra thư mục `out/` (không commit).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cdp import Browser  # noqa: E402

OUT = HERE / "out"
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("INK_QA_BASE", "http://127.0.0.1:3100")
URL = BASE + "/entertainment/ink-scout"


def new_browser(w: int = 1280, h: int = 720, mobile: bool = False, qa: bool = True) -> Browser:
    b = Browser(headless=True)
    if qa:
        b.send("Page.addScriptToEvaluateOnNewDocument", {"source": "window.__INK_QA__ = true;"})
    b.viewport(w, h, mobile=mobile)
    return b


def click_text(b: Browser, text: str, tag: str = "button") -> bool:
    box = b.eval(
        f"""(() => {{ const els = [...document.querySelectorAll({json.dumps(tag)})];
        const el = els.find(e => (e.innerText || e.textContent || '').trim().includes({json.dumps(text)}));
        if (!el) return null; el.scrollIntoView({{block:'nearest'}});
        const r = el.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }})()"""
    )
    if not box:
        return False
    b.click_at(box[0], box[1])
    return True


def start_game(b: Browser, settle: float = 1.5) -> None:
    """Menu -> (intro) -> man choi. Cho den khi API QA san sang."""
    b.goto(URL, settle=1.0, wait_expr="document.querySelector('.isc-menu')")
    if not (click_text(b, "▶ Chơi") or click_text(b, "▶ Tiếp tục")):
        raise RuntimeError("khong thay nut Choi/Tiep tuc")
    time.sleep(0.4)
    for _ in range(4):
        if b.eval("!!document.querySelector('.isc-intro')"):
            if not (click_text(b, "Xuống Kho") or click_text(b, "Tiếp →")):
                break
            time.sleep(0.3)
        else:
            break
    b.wait("window.__INK_QA_API__ && window.__INK_QA_API__.game", timeout=30)
    time.sleep(settle)


def shot(b: Browser, name: str) -> str:
    return b.shot(OUT / name)


def api(expr: str) -> str:
    return f"(() => {{ const A = window.__INK_QA_API__; const g = A.game; return ({expr}); }})()"
