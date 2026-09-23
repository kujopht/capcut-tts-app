import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from scripts.content_factory.overnight_runner import _get_channel_unprocessed_videos

vids = _get_channel_unprocessed_videos("https://www.youtube.com/@camanmmo/videos")
print(f"Found {len(vids)} unprocessed candidates on @camanmmo:", flush=True)
for v in vids:
    print(f"  * {v['title']} ({v['duration']/3600:.1f}h) -> {v['url']}", flush=True)
