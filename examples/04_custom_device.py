#!/usr/bin/env python3
"""
Example 04: Custom Device Configuration

This script demonstrates how to initialize CapCutClient with custom device parameters
from code or by loading an external device.json file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from capcut_tts_api import CapCutClient, DeviceConfig


def main():
    print("=== CapCut TTS API - Custom Device Profile Example ===")

    # Method A: Programmatic configuration using DeviceConfig
    custom_device = DeviceConfig(
        device_id="7647183892936328721",
        iid="7647185302080423697",
        tdid="7647183892936328721",
        appvr="8.7.0",
        loc="VN",
        lan="vi-VN"
    )

    client_a = CapCutClient(device=custom_device)
    print("Client A Device ID:", client_a.device.device_id)

    # Method B: Load from dictionary
    device_dict = {
        "device_id": "999888777666555444",
        "lan": "en-US",
        "loc": "US"
    }
    client_b = CapCutClient(device=device_dict)
    print("Client B Device ID:", client_b.device.device_id)
    print("Client B Language:", client_b.device.lan)


if __name__ == "__main__":
    main()
