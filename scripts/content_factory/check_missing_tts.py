import subprocess
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Get local chapters that have audio.mp3
local_base = Path("raw_spool/fanfic_tts")
local_chapters = [p.name for p in local_base.iterdir() if p.is_dir() and (p / "audio.mp3").exists()]

# Get drive chapters
cmd = ['rclone', 'lsf', 'fanfic-gdrive:FanficWorld/production/works/fanfic-tts', '--dirs-only']
res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
drive_chapters = set(d.rstrip('/') for d in res.stdout.splitlines())

missing = [c for c in local_chapters if c not in drive_chapters]
print(f"Local completed chapters: {len(local_chapters)}")
print(f"Drive completed chapters: {len(drive_chapters)}")
print(f"Missing from Drive: {len(missing)}")
for m in missing[:10]:
    print("  Missing:", m)
