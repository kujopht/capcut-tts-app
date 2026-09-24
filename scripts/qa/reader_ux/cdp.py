"""Minimal headless-Chrome CDP driver for visual QA (no extra deps beyond websocket-client)."""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Browser:
    def __init__(self, headless: bool = True):
        self.port = _free_port()
        self.profile = tempfile.mkdtemp(prefix="cdpqa-")
        args = [
            CHROME,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",
            "--mute-audio",
            "--hide-scrollbars",
            "--disable-features=Translate,MediaRouter",
            "--window-size=1600,1000",
        ]
        if headless:
            args.append("--headless=new")
        args.append("about:blank")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=2) as r:
                    json.loads(r.read())
                break
            except Exception:
                time.sleep(0.3)
        targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=5).read())
        page = next(t for t in targets if t.get("type") == "page")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self._id = 0
        self.events: list[dict] = []
        self.send("Page.enable")
        self.send("Runtime.enable")
        self.send("Network.enable")

    # ------------------------------------------------------------------ core
    def send(self, method: str, params: dict | None = None, timeout: float = 60):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self.events.append(msg)
        raise TimeoutError(method)

    def eval(self, expr: str, await_promise: bool = True):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": await_promise})
        if r.get("exceptionDetails"):
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:800])
        return r.get("result", {}).get("value")

    def viewport(self, w: int, h: int, mobile: bool = False):
        self.send("Emulation.setDeviceMetricsOverride", {
            "width": w, "height": h, "deviceScaleFactor": 1, "mobile": mobile,
            "screenWidth": w, "screenHeight": h})
        self.send("Emulation.setTouchEmulationEnabled", {"enabled": mobile})

    def emulate_media(self, reduced_motion: bool):
        self.send("Emulation.setEmulatedMedia", {"features": [
            {"name": "prefers-reduced-motion", "value": "reduce" if reduced_motion else "no-preference"}]})

    def goto(self, url: str, settle: float = 2.0, wait_expr: str | None = None, timeout: float = 45):
        self.events.clear()
        self.send("Page.navigate", {"url": url})
        time.sleep(0.5)
        target = url.split("#")[0]
        self.wait(f"location.href.startsWith({json.dumps(target.split('?')[0])}) && document.readyState !== 'loading'",
                  timeout=timeout)
        if wait_expr:
            self.wait(wait_expr, timeout=timeout)
        time.sleep(settle)

    def wait(self, expr: str, timeout: float = 30, interval: float = 0.25):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            try:
                last = self.eval(f"Boolean({expr})")
                if last:
                    return True
            except Exception as e:  # noqa
                last = str(e)
            time.sleep(interval)
        raise TimeoutError(f"wait({expr}) last={last}")

    def shot(self, path: str | Path, full: bool = False):
        params = {"format": "png", "captureBeyondViewport": full}
        if full:
            h = self.eval("document.documentElement.scrollHeight")
            w = self.eval("window.innerWidth")
            params["clip"] = {"x": 0, "y": 0, "width": w, "height": min(h, 12000), "scale": 1}
        data = self.send("Page.captureScreenshot", params)["data"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(data))
        return str(path)

    def wheel(self, x: int, y: int, dy: int, steps: int = 6):
        for _ in range(steps):
            self.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y,
                                                   "deltaX": 0, "deltaY": dy / steps})
            time.sleep(0.05)

    def click_at(self, x: float, y: float):
        for t in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left",
                                                   "clickCount": 1})

    def click(self, selector: str):
        box = self.eval(f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
            if (!el) return null; el.scrollIntoView({{block:'nearest'}});
            const r = el.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }})()""")
        if not box:
            raise RuntimeError(f"no element {selector}")
        self.click_at(box[0], box[1])
        return box

    def key(self, key: str, code: str, text: str = "", key_code: int = 0):
        base = {"key": key, "code": code, "windowsVirtualKeyCode": key_code, "nativeVirtualKeyCode": key_code}
        self.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": text, **base})
        self.send("Input.dispatchKeyEvent", {"type": "keyUp", **base})

    def console_errors(self):
        out = []
        for m in self.events:
            if m.get("method") == "Runtime.exceptionThrown":
                out.append(m["params"]["exceptionDetails"].get("text", "") + " " +
                           json.dumps(m["params"]["exceptionDetails"].get("exception", {}).get("description", ""))[:300])
            if m.get("method") == "Runtime.consoleAPICalled" and m["params"].get("type") == "error":
                out.append(" ".join(str(a.get("value", a.get("description", ""))) for a in m["params"]["args"])[:300])
        return out

    def close(self):
        try:
            self.send("Browser.close", timeout=5)
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)
