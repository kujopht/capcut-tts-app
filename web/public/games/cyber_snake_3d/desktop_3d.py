import os
import sys
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent
HTML_FILE = GAME_DIR / "index.html"

def launch():
    try:
        import webview
        print("[*] Starting CYBER SERPENT 3D in Dedicated Native Window...")
        webview.create_window(
            title="CYBER SERPENT 3D - Titan Edition",
            url=str(HTML_FILE),
            width=1180,
            height=880,
            resizable=True,
            easy_drag=True,
            background_color='#03050d',
            min_size=(840, 620)
        )
        webview.start(debug=False)
    except Exception as e:
        print(f"[*] Opening in default high-performance browser: {e}")
        import webbrowser
        webbrowser.open(HTML_FILE.as_uri())

if __name__ == '__main__':
    launch()
