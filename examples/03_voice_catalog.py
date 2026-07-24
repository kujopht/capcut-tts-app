#!/usr/bin/env python3
"""
Example 03: Inspecting & Filtering Voice Catalog

This script demonstrates how to search, list, and filter available CapCut TTS voices
by language or display name.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from capcut_tts_api import CapCutClient


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== CapCut TTS API - Voice Catalog Inspector ===")

    client = CapCutClient()

    # 1. Filter Vietnamese voices
    vi_voices = client.list_voices(lang="vi-VN")
    print(f"\nFound {len(vi_voices)} Vietnamese voices:")
    print("-" * 65)
    print(f"{'Display Name':<25} | {'Voice Type':<28} | Resource ID")
    print("-" * 65)
    for v in vi_voices[:10]: # Display top 10
        print(f"{v.display_name:<25} | {v.voice_type:<28} | {v.resource_id}")

    # 2. Search resource_id by voice_type
    voice_type_query = "BV421_vivn_streaming"
    print(f"\nResolving resource_id for voice_type = '{voice_type_query}'...")
    voice_type, res_id = client.resolve_voice(voice=voice_type_query)
    print(f"Result: voice_type = '{voice_type}', resource_id = '{res_id}'")


if __name__ == "__main__":
    main()
