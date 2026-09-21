#!/usr/bin/env python3
"""
Post-Deploy Visual QA Screenshot Capture for Live Production (https://fanfic.world)
Uses Chrome DevTools Protocol (CDP) to capture exact rendered state across viewports.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
import urllib.request
import websockets

CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENSHOT_DIR = Path(
    r"C:\Users\nguye\.agy-sessions\acc3\.gemini\antigravity-cli\brain\a3f633d6-32fe-4885-b388-919b38c09c04\screenshots_live_prod"
)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

RESOLUTIONS = [
    ("1600x900", 1600, 900),
    ("1440x900", 1440, 900),
    ("1366x768", 1366, 768),
    ("1024x768", 1024, 768),
    ("390x844", 390, 844),
]

CORE_PAGES = [
    ("live_home", "https://fanfic.world/", ".showcase-cover"),
    ("live_library", "https://fanfic.world/library", ".lib-card"),
]

DETAIL_PAGES = [
    ("detail_hatake_1440x900", "https://fanfic.world/novels/nov_hatake_156690", 1440, 900),
    ("detail_hatake_390x844", "https://fanfic.world/novels/nov_hatake_156690", 390, 844),
    ("detail_cold_1440x900", "https://fanfic.world/novels/nov_rr_156206", 1440, 900),
    ("detail_cold_390x844", "https://fanfic.world/novels/nov_rr_156206", 390, 844),
    ("detail_genshin_1440x900", "https://fanfic.world/novels/nov_genshin_01", 1440, 900),
]


async def capture_page(ws_url: str, url: str, wait_selector: str, out_path: Path, width: int, height: int):
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        msg_id = 1

        async def send(method, params=None):
            nonlocal msg_id
            m_id = msg_id
            msg_id += 1
            payload = {"id": m_id, "method": method}
            if params:
                payload["params"] = params
            await ws.send(json.dumps(payload))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == m_id:
                    return resp.get("result", {})

        await send("Page.enable")
        await send("Runtime.enable")

        await send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": width <= 640,
            },
        )

        await send("Page.navigate", {"url": url})

        # Wait for selector or max 15 seconds
        start = time.time()
        ready = False
        if wait_selector:
            while time.time() - start < 15:
                res = await send(
                    "Runtime.evaluate",
                    {
                        "expression": f"Boolean(document.querySelector('{wait_selector}'))",
                        "returnByValue": True,
                    },
                )
                if res.get("result", {}).get("value") is True:
                    ready = True
                    break
                await asyncio.sleep(0.3)

        # Allow network requests and CSS transitions to settle
        await asyncio.sleep(1.5)

        shot_res = await send("Page.captureScreenshot", {"format": "png"})
        img_b64 = shot_res.get("data", "")
        if img_b64:
            img_bytes = base64.b64decode(img_b64)
            out_path.write_bytes(img_bytes)
            print(f"Captured {out_path.name} ({width}x{height}) [ready={ready}, size={len(img_bytes)//1024} KB]", flush=True)
        else:
            print(f"Failed capturing {out_path.name}", flush=True)


def main():
    print("Launching Chrome headless for Live Production QA...", flush=True)
    user_data = Path(r"C:\Users\nguye\AppData\Local\Temp\chrome_live_qa_profile")
    if user_data.exists():
        shutil.rmtree(user_data, ignore_errors=True)
    user_data.mkdir(parents=True, exist_ok=True)

    chrome_cmd = [
        CHROME_BIN,
        "--headless=new",
        "--remote-debugging-port=9226",
        f"--user-data-dir={user_data}",
        "--disable-extensions",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]

    proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    try:
        with urllib.request.urlopen("http://127.0.0.1:9226/json", timeout=5) as r:
            tabs = json.loads(r.read().decode("utf-8"))
            page_tab = next((t for t in tabs if t.get("type") == "page"), tabs[0])
            ws_url = page_tab["webSocketDebuggerUrl"]
            print(f"Connected to debugger: {ws_url}", flush=True)

        async def run_all():
            # 1. Capture 5 viewports for Home and Library
            for p_name, url, selector in CORE_PAGES:
                for r_name, w, h in RESOLUTIONS:
                    out_file = SCREENSHOT_DIR / f"{p_name}_{r_name}.png"
                    await capture_page(ws_url, url, selector, out_file, w, h)

            # 2. Capture detail pages
            for name, url, w, h in DETAIL_PAGES:
                out_file = SCREENSHOT_DIR / f"{name}.png"
                await capture_page(ws_url, url, ".detail-card, .novel-detail, .page", out_file, w, h)

        asyncio.run(run_all())
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        print("Completed live production screenshot capture.", flush=True)


if __name__ == "__main__":
    main()
