import os
import sys
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent
HTML_FILE = GAME_DIR / "index.html"

def launch():
    try:
        import webview
        print("[*] Starting ASTRAL DRAGON 3D: SOLAR ODYSSEY in Dedicated Window...")
        webview.create_window(
            title="ASTRAL DRAGON 3D - Solar Odyssey (No Man's Sky Edition)",
            url=str(HTML_FILE),
            width=1240,
            height=880,
            resizable=True,
            easy_drag=True,
            background_color='#02030a',
            min_size=(880, 640)
        )
        webview.start(debug=False)
    except Exception as e:
        print(f"[*] Opening in default web browser: {e}")
        import webbrowser
        webbrowser.open(HTML_FILE.as_uri())

if __name__ == '__main__':
    launch()
