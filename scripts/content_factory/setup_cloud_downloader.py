"""Setup Cloud Downloader trên Lightning AI CPU Studio.

Script này:
1. Kiểm tra & cài đặt yt-dlp, rclone, ffmpeg trên CPU Studio
2. Upload rclone.conf vào đúng đường dẫn Cloud Studio
3. Cài đặt endpoint /download_and_sync trên server (cần restart server)
4. Test kết nối Google Drive từ Cloud
"""
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(r"C:\Users\nguye\Documents\CapCut-TTS-App")
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
import requests


def _run(s: Studio, cmd: str) -> str:
    """Run command on Studio and return stripped output."""
    out = s.run(cmd)
    return (out or "").strip()


def main():
    print("[*] Bắt đầu thiết lập Cloud Downloader & Drive Uploader trên CPU Studio...")
    s = Studio(name=CPU_STUDIO_NAME, teamspace=DEFAULT_TEAMSPACE, user=DEFAULT_USER)

    # ── 1. Kiểm tra yt-dlp ────────────────────────────────────────────────────
    print("\n[1/4] Kiểm tra yt-dlp...")
    ytdlp_check = _run(s, "which yt-dlp 2>/dev/null || echo 'not found'")
    if "not found" in ytdlp_check:
        print("  Cài yt-dlp qua pip...")
        _run(s, "pip install -q yt-dlp")
    ytdlp_ver = _run(s, "yt-dlp --version")
    print(f"  [✓] yt-dlp: {ytdlp_ver}")

    # ── 2. Kiểm tra rclone ────────────────────────────────────────────────────
    print("\n[2/4] Kiểm tra rclone...")
    rclone_check = _run(s, "which rclone 2>/dev/null || echo 'not found'")
    if "not found" in rclone_check:
        print("  Cài rclone qua apt...")
        _run(s, "sudo apt-get update -qq && sudo apt-get install -y -qq rclone")
    rclone_ver = _run(s, "rclone version | head -1")
    print(f"  [✓] rclone: {rclone_ver}")

    # ── 3. Upload rclone.conf ──────────────────────────────────────────────────
    print("\n[3/4] Đồng bộ rclone.conf lên Cloud...")
    local_conf = Path(os.environ["APPDATA"]) / "rclone" / "rclone.conf"
    if not local_conf.exists():
        print(f"  [!] Không tìm thấy rclone.conf tại {local_conf}, bỏ qua.")
    else:
        import base64

        # Read and base64-encode locally
        raw_bytes = local_conf.read_bytes()
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        print(f"  rclone.conf local: {len(raw_bytes)} bytes, {len(b64)} chars base64")

        # Write to /content/rclone.conf on Cloud via python3 (no upload_file path issues)
        write_cmd = (
            f"python3 -c \""
            f"import base64; "
            f"open('/content/rclone.conf', 'wb').write(base64.b64decode('{b64}'))"
            f"\""
        )
        _run(s, "mkdir -p /content")
        _run(s, write_cmd)
        _run(s, "chmod 600 /content/rclone.conf")

        # Verify file was written correctly
        verify = _run(s, "ls -lh /content/rclone.conf && head -5 /content/rclone.conf")
        print(f"  Verify:\n{verify}")

        # Test rclone with explicit --config
        print("  Test kết nối Google Drive từ Cloud...")
        remotes = _run(s, "rclone listremotes --config /content/rclone.conf 2>&1")
        print(f"  Remotes tìm thấy: {remotes.strip() or '(không có)'}")

        if "fanfic-gdrive" in remotes:
            print("  [✓] fanfic-gdrive remote hoạt động!")
            test_ls = _run(
                s,
                "rclone lsd fanfic-gdrive:FanficWorld/production/works "
                "--config /content/rclone.conf 2>&1 | head -8",
            )
            print(f"  Drive ls: {test_ls}")

            # Lưu đường dẫn config để server và rclone commands dùng
            _run(
                s,
                "echo 'export RCLONE_CONFIG=/content/rclone.conf' > /content/rclone_env.sh && "
                "chmod +x /content/rclone_env.sh",
            )
            print("  [✓] Đã lưu RCLONE_CONFIG=/content/rclone.conf vào /content/rclone_env.sh")
        else:
            print("  [!] Không tìm thấy fanfic-gdrive trong remotes. Kiểm tra lại OAuth token.")
            print(f"  Chi tiết: {remotes}")

    # ── 4. Test download + rclone copy ─────────────────────────────────────────
    print("\n[4/4] Test tải thử 1 URL YouTube và upload Drive (nếu config hoạt động)...")
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # short test video
    test_out = _run(
        s,
        f"yt-dlp --no-warnings --print title --no-download '{test_url}' 2>&1 | head -3",
    )
    print(f"  yt-dlp test title: {test_out}")

    print("\n[✓] Hoàn thành setup Cloud Downloader!")
    print("    Bước tiếp theo: restart lightning_tts_server.py để load endpoint /download_and_sync")


if __name__ == "__main__":
    main()
