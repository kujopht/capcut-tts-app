import subprocess
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

def run_rclone(cmd_args):
    cmd = ["rclone"] + cmd_args
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return res.stdout, res.stderr

print("=== 1. AI ANIMATION ON DRIVE ===")
out, _ = run_rclone(["ls", "fanfic-gdrive:FanficWorld/production/works/ai-animation"])
for line in out.strip().splitlines()[:30]:
    print(" ", line)
print(f"Total files in ai-animation on Drive: {len(out.strip().splitlines())}")

print("\n=== 2. CHECK CONAN CH 16 ON DRIVE ===")
out, _ = run_rclone(["lsf", "fanfic-gdrive:FanficWorld/production/works/fanfic-tts", "--dirs-only", "--include", "*Chương 16*"])
print("Conan Ch 16 search on Drive:", out.strip())

print("\n=== 3. CHECK SINGLE PIECES IN EXISTING-AUDIO OR CHINESE-MEDIA ===")
out, _ = run_rclone(["lsf", "fanfic-gdrive:FanficWorld/production/works/chinese-media", "--dirs-only"])
print("Folders in chinese-media on Drive:")
for line in out.strip().splitlines()[:15]:
    print(" ", line)
