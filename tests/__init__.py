"""
Unit test cho Fanfic Audio Studio.

KHONG co test nao goi API CapCut that: moi request deu duoc mock.

Chay toan bo:
    .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import sys
from pathlib import Path

# Cho phep `import desktop_app` khi chay unittest tu thu muc du an
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
