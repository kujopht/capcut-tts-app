#!/usr/bin/env python3
"""
Responsive QA Screenshot Capture for Fanfic World using Chrome DevTools Protocol (CDP).
Uses --disable-web-security to allow headless browser to query production Render backend directly.
Waits for real API hydration (.showcase-cover for home, .lib-card for library).
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
    r"C:\Users\nguye\.agy-sessions\acc3\.gemini\antigravity-cli\brain\a3f633d6-32fe-4885-b388-919b38c09c04\screenshots"
)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

RESOLUTIONS = [
    ("1600x900", 1600, 900),
    ("1440x900", 1440, 900),
    ("1366x768", 1366, 768),
    ("1024x768", 1024, 768),
    ("390x844", 390, 844),
]

PAGES = [
    ("home", "http://localhost:3005/", ".showcase-cover"),
    ("library", "http://localhost:3005/library", ".lib-card"),
]


async def capture_page_cdp(ws_url: str, url: str, wait_selector: str, out_path: Path, width: int, height: int):
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

        # Wait for selector to exist and have elements
        start = time.time()
        ready = False
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

        # Let layout/animation settle
        await asyncio.sleep(0.6)

        shot_res = await send("Page.captureScreenshot", {"format": "png"})
        img_b64 = shot_res.get("data", "")
        if img_b64:
            img_bytes = base64.b64decode(img_b64)
            out_path.write_bytes(img_bytes)
            print(f"Captured {out_path.name} ({width}x{height}) [ready={ready}, size={len(img_bytes)//1024} KB]", flush=True)
        else:
            print(f"Failed capturing {out_path.name}", flush=True)


def main():
    print("Launching Chrome headless with remote debugging & disable-web-security...", flush=True)
    user_data = Path(r"C:\Users\nguye\AppData\Local\Temp\chrome_cdp_profile_qa")
    if user_data.exists():
        shutil.rmtree(user_data, ignore_errors=True)
    user_data.mkdir(parents=True, exist_ok=True)

    chrome_cmd = [
        CHROME_BIN,
        "--headless=new",
        "--remote-debugging-port=9225",
        f"--user-data-dir={user_data}",
        "--disable-web-security",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]

    chrome_proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    try:
        with urllib.request.urlopen("http://127.0.0.1:9225/json", timeout=5) as r:
            tabs = json.loads(r.read().decode("utf-8"))
            page_tab = next((t for t in tabs if t.get("type") == "page"), tabs[0])
            ws_url = page_tab["webSocketDebuggerUrl"]
            print(f"Connected to page: {page_tab.get('title')} ({ws_url})", flush=True)

        async def run_all():
            for p_name, url, selector in PAGES:
                for r_name, w, h in RESOLUTIONS:
                    out_file = SCREENSHOT_DIR / f"{p_name}_{r_name}.png"
                    await capture_page_cdp(ws_url, url, selector, out_file, w, h)

        asyncio.run(run_all())
    finally:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=5)
        print("Done QA screenshot capture.", flush=True)


if __name__ == "__main__":
    main()
