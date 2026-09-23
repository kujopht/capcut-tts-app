"""Content Factory Router V4 Package.

Automated 3-worker content generation pipeline for fanfic.world:
- Worker 1: YouTube Audio Harvester + Gemini 3.8 Flash Filter + Description/Transcript
- Worker 2: Raw Fanfic Scraper (FanFicFare) + Translation + TTS Ngoc Huyen + Synchronized Transcript
- Worker 3: AI Animation Harvester + Watermark/CN Sub Mask + SubVid Vietsub + Multi-voice Dubbing
"""

# Globally enforce silent execution without console window flashes
import scripts.content_factory.silent_subprocess

