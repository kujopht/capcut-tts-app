#!/usr/bin/env python3
"""
Example 02: Speech-to-Text (STT) Subtitle Extraction

This script demonstrates how to upload a local audio file (.mp3, .m4a, .mp4),
create a subtitle recognition (STT) task, and parse structured subtitles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from capcut_tts_api import CapCutClient, SubtitleResult


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== CapCut TTS API - STT Subtitle Extraction Example ===")

    client = CapCutClient()
    sample_file = "sample.mp3"

    print(f"\n1. Building STT request for file: {sample_file}")
    # Example preview using mock/dry-run parameters
    url, headers, body_text = client.build_stt_new_request(
        audio_vid="v10639g500000000000000000000",
        audio_md5="6171f4249ae1561cab6c4e4f1e1d71fa",
        duration_ms=12500,
        language="vi-VN"
    )
    print("   Generated STT Request URL:", url[:70], "...")

    print("\n2. Parsing sample STT response JSON payload...")
    mock_stt_payload = {
        "utterances": [
            {
                "text": "Xin chào mọi người",
                "start_time": 0,
                "end_time": 1500,
                "words": [
                    {"text": "Xin", "start_time": 0, "end_time": 400},
                    {"text": "chào", "start_time": 400, "end_time": 800},
                    {"text": "mọi", "start_time": 800, "end_time": 1100},
                    {"text": "người", "start_time": 1100, "end_time": 1500}
                ]
            },
            {
                "text": "Hôm nay chúng ta sẽ tìm hiểu về CapCut API",
                "start_time": 1600,
                "end_time": 4500,
                "words": []
            }
        ]
    }

    mock_query_response = {
        "status_code": 0,
        "data": {
            "tasks": [
                {
                    "status": "success",
                    "payload": mock_stt_payload
                }
            ]
        }
    }

    # Extract structured subtitles
    subtitles: SubtitleResult = client.extract_subtitles(mock_query_response)

    print("\n--- Parsed Subtitle Result ---")
    print(f"Full Text: {subtitles.full_text}\n")
    print("Utterances with Timings:")
    for idx, item in enumerate(subtitles.utterances, 1):
        print(f"  [{idx}] ({item.start_time}ms -> {item.end_time}ms): {item.text}")


if __name__ == "__main__":
    main()
