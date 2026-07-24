#!/usr/bin/env python3
"""
Example 01: Basic Text-to-Speech (TTS) Generation

This script demonstrates how to generate speech using CapCut voice display names
or voice types with automatic resource_id resolution.
"""

import sys
from pathlib import Path

# Add project root to sys.path if running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from capcut_tts_api import CapCutClient, CapCutError


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== CapCut TTS API - Basic TTS Example ===")

    # Initialize client
    client = CapCutClient()

    # Text to convert to speech
    text = "Xin chào bạn! Thư viện CapCut TTS API giúp tạo giọng đọc dễ dàng."

    # Specify voice_type (e.g. "BV421_vivn_streaming" or "BV074_streaming")
    voice_type_input = "BV421_vivn_streaming"

    print(f"1. Resolving voice_type: '{voice_type_input}'...")
    voice_type, resource_id = client.resolve_voice(voice=voice_type_input)
    print(f"   -> Resolved Voice Type: {voice_type}")
    print(f"   -> Resolved Resource ID: {resource_id}")

    print("\n2. Building TTS request payload (Dry-Run preview)...")
    url, headers, body_text = client.build_tts_new_request(
        texts=text,
        voice=voice_type_input,
        rate="1.0"
    )
    print(f"   Target API URL: {url[:70]}...")
    print(f"   Header 'sign' present: {'sign' in headers}")

    print("\n3. Executing TTS task generation...")
    try:
        # Generate speech and wait for result
        result = client.generate_speech(
            texts=text,
            voice=voice_type_input,
            wait=False # Set to True when connecting to live API endpoint
        )
        print("   Task Submitted Successfully!")
        print("   Response:", result)
    except CapCutError as exc:
        print(f"   Client Error: {exc}")
    except Exception as exc:
        print(f"   Network/API Error: {exc}")


if __name__ == "__main__":
    main()
