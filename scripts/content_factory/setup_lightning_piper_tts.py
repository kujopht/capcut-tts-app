"""
Automated Deployment of Piper TTS (Ngọc Huyền Mới) to Lightning AI CPU Studio.

1. Connects to 'scratch-studio-devbox' (4 vCPUs, 16GB RAM).
2. Installs piper-tts, ffmpeg, fastapi, uvicorn, edge-tts.
3. Uploads ngochuyennew.onnx and ngochuyennew.onnx.json to /content/models/piper/.
4. Deploys updated lightning_tts_server.py on port 8000.
5. Verifies end-to-end cloud synthesis of pure Ngọc Huyền (Mới).
"""

import os
import sys
import time
from pathlib import Path

# Force UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.lightning_helper import (
    CPU_STUDIO_NAME,
    CPU_TTS_URL,
    DEFAULT_TEAMSPACE,
    DEFAULT_USER,
    _configure_credentials,
)

_configure_credentials()
from lightning_sdk import Studio


def main():
    print(f"[*] Đang kết nối tới CPU Studio '{CPU_STUDIO_NAME}' trên Lightning AI...")
    s = Studio(name=CPU_STUDIO_NAME, teamspace=DEFAULT_TEAMSPACE, user=DEFAULT_USER)
    print(f"[+] Trạng thái hiện tại: {s.status}")

    if str(s.status).lower() != "running" and "running" not in str(s.status).lower():
        print("[*] Đang khởi động CPU Studio...")
        s.start()
        time.sleep(10)

    # 1. Install dependencies on remote CPU Studio
    print("[*] Cài đặt piper-tts & dependencies trên CPU Studio...")
    out = s.run("pip install --quiet piper-tts fastapi uvicorn edge-tts requests")
    print(f"[+] Kết quả cài đặt:\n{out[:300]}")

    # Check piper command
    piper_check = s.run("which piper || python3 -m piper --version || echo 'piper-check-done'")
    print(f"[+] Kiểm tra piper remote: {piper_check.strip()}")

    # 2. Upload model files
    local_model_dir = Path(os.environ["LOCALAPPDATA"]) / "FanficAudioStudio" / "models" / "piper"
    onnx_file = local_model_dir / "ngochuyennew.onnx"
    json_file = local_model_dir / "ngochuyennew.onnx.json"

    if not onnx_file.exists():
        print(f"[!] Lỗi: Không tìm thấy {onnx_file}")
        return

    print("[*] Tạo thư mục /content/models/piper trên CPU Studio...")
    s.run("mkdir -p /content/models/piper")

    # Check if already exists on remote to save bandwidth
    check_remote_files = s.run("ls -lh /content/models/piper/ || true")
    print(f"[+] Tình trạng file hiện tại trên remote:\n{check_remote_files}")

    if "ngochuyennew.onnx" not in check_remote_files or "0 " in check_remote_files:
        print(f"[*] Đang tải lên {onnx_file.name} ({onnx_file.stat().st_size / (1024*1024):.1f} MB)...")
        s.upload_file(str(onnx_file), "/content/models/piper/ngochuyennew.onnx")
        print("[+] Đã tải lên file ONNX thành công!")

    if "ngochuyennew.onnx.json" not in check_remote_files:
        print(f"[*] Đang tải lên {json_file.name}...")
        s.upload_file(str(json_file), "/content/models/piper/ngochuyennew.onnx.json")
        print("[+] Đã tải lên file JSON thành công!")

    # 3. Upload updated lightning_tts_server.py
    server_file = PROJECT_ROOT / "scripts" / "content_factory" / "lightning_tts_server.py"
    print(f"[*] Đang tải lên {server_file.name}...")
    s.upload_file(str(server_file), "/content/lightning_tts_server.py")
    print("[+] Tải lên server script thành công!")

    # 4. Restart server on port 8000
    print("[*] Khởi động lại TTS server trên port 8000 của CPU Studio...")
    s.run("pkill -f 'lightning_tts_server.py' || true")
    time.sleep(2)
    s.run_and_detach("python3 /content/lightning_tts_server.py")
    time.sleep(5)

    # 5. Verify health & test synthesis
    print(f"[*] Kiểm tra endpoint: {CPU_TTS_URL}/health...")
    import requests
    for i in range(12):
        try:
            r = requests.get(f"{CPU_TTS_URL}/health", timeout=5)
            if r.status_code == 200:
                print(f"[✓] CPU Studio TTS Server đã sẵn sàng: {r.json()}")
                break
        except Exception as e:
            print(f"    Chờ server khởi động ({i+1}/12)... {e}")
            time.sleep(3)

    # Test synthesis remotely
    print("[*] Thử nghiệm tổng hợp 1 câu giọng Ngọc Huyền (Mới) trên CPU Cloud...")
    test_resp = requests.post(
        f"{CPU_TTS_URL}/synthesize",
        data={
            "text": "Xin chào, đây là giọng Ngọc Huyền mới chạy trên CPU của Lightning AI.",
            "voice": "ngochuyennew",
        },
        timeout=30,
    )
    if test_resp.status_code == 200 and len(test_resp.content) > 1000:
        print(f"[✓] THÀNH CÔNG RỰC RỠ! Cloud TTS trả về file audio: {len(test_resp.content)} bytes!")
    else:
        print(f"[!] Thử nghiệm thất bại: Status {test_resp.status_code}, nội dung: {test_resp.text[:200]}")


if __name__ == "__main__":
    main()
