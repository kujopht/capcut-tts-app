import subprocess
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

def run_rclone(cmd_args):
    cmd = ["rclone"] + cmd_args
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return res.stdout, res.stderr

print("Checking Google Drive folders...")

# 1. Check existing-audio
out, _ = run_rclone(["lsf", "fanfic-gdrive:FanficWorld/production/works/existing-audio", "--dirs-only"])
print(f"\n--- Drive existing-audio dirs ({len(out.strip().splitlines())}) ---")
for line in out.strip().splitlines()[:15]:
    print(" ", line)

# 2. Check fanfic-tts
out, _ = run_rclone(["lsf", "fanfic-gdrive:FanficWorld/production/works/fanfic-tts", "--dirs-only"])
print(f"\n--- Drive fanfic-tts dirs ({len(out.strip().splitlines())}) ---")
for line in out.strip().splitlines()[:15]:
    print(" ", line)

# 3. Check ai-animation
out, _ = run_rclone(["lsf", "fanfic-gdrive:FanficWorld/production/works/ai-animation", "--dirs-only"])
print(f"\n--- Drive ai-animation dirs ({len(out.strip().splitlines())}) ---")
for line in out.strip().splitlines()[:15]:
    print(" ", line)
