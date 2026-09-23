import sys
import os
from pathlib import Path
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')
from scripts.content_factory.lightning_helper import (
    _configure_credentials,
    CPU_STUDIO_NAME,
    DEFAULT_TEAMSPACE,
    DEFAULT_USER,
)

_configure_credentials()
from lightning_sdk import Studio

s = Studio(name=CPU_STUDIO_NAME, teamspace=DEFAULT_TEAMSPACE, user=DEFAULT_USER)

# Upload a test runner to remote studio
remote_test_code = """
import sys
sys.path.insert(0, "/teamspace/studios/this_studio")
try:
    from capcut_tts_api.client import CapCutClient
    c = CapCutClient()
    print("CapCutClient created successfully.")
    print("Testing generate_speech for BV075_streaming...")
    res = c.generate_speech(["Xin chào, đây là giọng nam."], voice="BV075_streaming", timeout=25.0)
    print("Result keys:", res.keys())
    import json
    payload = json.loads(res["data"]["tasks"][0]["payload"])
    sub = payload["audio_subtitles"][0]
    print("speech_url:", sub.get("speech_url")[:60])
except Exception as e:
    import traceback
    traceback.print_exc()
"""
Path("raw_spool/remote_test.py").write_text(remote_test_code, encoding="utf-8")
s.upload_file("raw_spool/remote_test.py", "remote_test.py")

print("Running test on CPU studio:")
out = s.run("python3 /teamspace/studios/this_studio/remote_test.py")
print(out)
