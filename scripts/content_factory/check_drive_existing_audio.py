import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')

cmd = ["rclone", "lsf", "fanfic-gdrive:FanficWorld/production/works/existing-audio", "--recursive", "--files-only"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
lines = res.stdout.splitlines()
print(f"Total files in existing-audio on Drive: {len(lines)}")
for line in lines[:30]:
    print(" ", line)
