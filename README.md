# CapCut TTS API Client & Python SDK (`capcut-tts-api`)

A professional, pure Python module SDK and Command-Line Interface (CLI) for CapCut common task workflows:

- **Text to Speech (TTS)**: High-quality audio generation using CapCut voice catalog with automatic `voice_type` and `resource_id` resolution.
- **Speech to Text (STT)**: Automatic subtitle recognition and speech transcription.
- **VOD Chunked Media Upload**: Multi-stage audio/video uploading with AWS SigV4 signing.
- **Task Polling & Management**: Asynchronous task querying with automatic status polling.
- **Subtitle Parser**: Structured extraction of timestamps, utterances, and word timings.
- **Voice Library Catalog**: Helper tools to query and inspect available CapCut voices.

> **Pure Python**: Zero native dependencies (`.dylib`, `.so`, `.dll`), no C++ binaries, and no `ctypes`. Request signing, payload encryption (RSA PKCS#1 v1.5), and VOD authentication (AWS SigV4) are implemented 100% natively in standard Python.

> *Use this SDK and tool responsibly with authorized accounts, sessions, and media.*

---

## Donate / Ủng hộ

If this project helps your work, you can support development with USDT on TRC20:

```text
TL4sPkfSTVnmneKvvuCfa2wSDnADjxDqYV
```
Network: **TRC20**

---

## English Documentation

### Features

- **High-Level Python SDK (`capcut_tts_api`)**: Clean, object-oriented API for seamless integration into Python applications.
- **Automatic Voice & Resource ID Resolution**: Pass `voice="BV421_vivn_streaming"` (the `voice_type`), and the SDK automatically resolves the matching `resource_id` from `Voice.json`!
- **Command Line Interface (`capcut-tts-api` CLI)**: Full-featured CLI command (`capcut-tts-api` or `python -m capcut_tts_api.cli`) for terminal usage and automation scripts.
- **Pure Python Cryptography**: RSA PKCS#1 v1.5 encryption & AWS SigV4 signer implemented without external crypto C-extensions.
- **Typed Data Models**: Dataclasses for `DeviceConfig`, `UploadResult`, `Utterance`, `Word`, `SubtitleResult`, and `VoiceInfo`.

---

### Installation

Requires Python 3.9+.

```bash
# Option 1: Install as a Python package in editable mode
python3 -m pip install -e .

# Option 2: Direct dependency installation
python3 -m pip install requests
```

---

### Examples & Sample Files

The repository includes ready-to-run example scripts in the `examples/` directory:

- [examples/01_tts_basic.py](examples/01_tts_basic.py): Basic TTS generation with automatic voice_type resolution.
- [examples/02_stt_transcribe.py](examples/02_stt_transcribe.py): Media file transcription and structured subtitle parsing.
- [examples/03_voice_catalog.py](examples/03_voice_catalog.py): Searching, filtering, and listing available voices in catalog.
- [examples/04_custom_device.py](examples/04_custom_device.py): Custom device identity configuration.
- [device.json.example](device.json.example): Sample JSON file for overriding device identity.

Run any example:

```bash
python examples/01_tts_basic.py
python examples/03_voice_catalog.py
```

---

### Python SDK Quickstart

#### 1. Text to Speech (TTS)

##### Automatic Voice & Resource ID Resolution

Specify `voice` as `voice_type` (e.g. `"BV421_vivn_streaming"`, `"BV074_streaming"`). The SDK automatically looks up `Voice.json` and links the corresponding `resource_id`!

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# Generate speech using voice_type (auto-resolves resource_id="7252594014782755330")
response = client.generate_speech(
    texts="Xin chào bạn! Chúc bạn một ngày vui vẻ.",
    voice="BV421_vivn_streaming", # voice_type
    rate="1.0",
    wait=True
)

print(response)
```

##### Low-Level Async/Manual Polling Flow

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# 1. Submit TTS task with voice_type (auto-resolves resource_id)
task_res = client.create_tts_task(
    texts=["Segment 1 of speech", "Segment 2 of speech"],
    voice="BV074_streaming"
)

task = task_res["data"]["tasks"][0]
task_id = task["id"]
token = task["token"]

# 2. Query task status manually
query_res = client.query_tts_task(task_id, token)
print(query_res)
```

---

#### 2. Speech to Text (STT) & Subtitle Extraction

##### Transcribe Local Media File (.mp3, .m4a, .mp4)

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# Upload media, create STT task, and wait for completed result
res = client.transcribe_file(
    file_path="sample_audio.mp3",
    language="vi-VN",
    use_translation=False,
    wait=True
)

# Parse structured subtitles directly from query response
subtitles = client.extract_subtitles(res)

print("Full Transcribed Text:", subtitles.full_text)
for utterance in subtitles.utterances:
    print(f"[{utterance.start_time}ms -> {utterance.end_time}ms] {utterance.text}")
```

---

#### 3. Media Upload to CapCut VOD Space

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# Upload audio/video to CapCut VOD storage
upload_res = client.upload_audio("video.mp4")

print(f"VID: {upload_res.vid}")
print(f"MD5: {upload_res.md5}")
print(f"Duration: {upload_res.duration_ms} ms")
```

---

#### 4. Custom Device Configuration

Override default device parameters programmatically:

```python
from capcut_tts_api import CapCutClient, DeviceConfig

custom_device = DeviceConfig(
    device_id="7647183892936328721",
    iid="7647185302080423697",
    appvr="8.7.0",
    loc="VN",
    lan="vi-VN"
)

client = CapCutClient(device=custom_device)
```

Or load from a JSON file (`device.json`):

```python
client = CapCutClient(device="device.json")
```

---

#### 5. Inspecting Available Voices

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# List Vietnamese voices from Voice.json catalog
voices = client.list_voices(lang="vi-VN")

for voice in voices:
    print(f"{voice.display_name} ({voice.voice_type}) -> Resource ID: {voice.resource_id}")
```

---

### Command-Line Interface (CLI) Guide

You can run commands using `capcut-tts-api` (after `pip install -e .`) or `python -m capcut_tts_api.cli`:

#### 1. List Available Voices

```bash
capcut-tts-api list-voices --language vi-VN
# OR: python -m capcut_tts_api.cli list-voices --language vi-VN
```

#### 2. Create TTS Task (Auto-resolves resource_id from voice_type)

```bash
capcut-tts-api tts-new \
  --text "Xin chào thế giới" \
  --voice "BV421_vivn_streaming" \
  --rate 1.0
```

#### 3. Query TTS Task

```bash
capcut-tts-api tts-query \
  --task-id "TASK_ID" \
  --token "TOKEN"
```

#### 4. Upload Audio File

```bash
capcut-tts-api upload-audio \
  --audio-file 1.mp4
```

#### 5. Upload & Transcribe (STT) in One Step

```bash
capcut-tts-api stt-file \
  --audio-file 1.mp4 \
  --language vi-VN \
  --out response.json
```

#### 6. Query STT Task

```bash
capcut-tts-api stt-query \
  --task-id "TASK_ID" \
  --token "TOKEN"
```

#### 7. Dry-Run Mode (Preview signed request without calling API)

```bash
capcut-tts-api tts-new \
  --text "Dry run test" \
  --voice "BV421_vivn_streaming" \
  --dry-run
```

---

### Module Architecture

```text
capcut-tts-api-main/
├── capcut_tts_api/              # Core Python Package (capcut-tts-api)
│   ├── __init__.py              # SDK exports & version metadata
│   ├── config.py                # Base URLs, VOD constants, RSA public key
│   ├── exceptions.py            # CapCut error hierarchy
│   ├── models.py                # Strongly-typed dataclasses (DeviceConfig, Utterance, etc.)
│   ├── signer.py                # RSA PKCS#1 v1.5, AWS SigV4, MD5 stubs & request signing
│   ├── uploader.py              # Chunked VOD media uploader
│   ├── client.py                # High-level CapCutClient SDK
│   └── cli.py                   # Argument parser & CLI logic
├── examples/                    # Runnable code examples
│   ├── 01_tts_basic.py
│   ├── 02_stt_transcribe.py
│   ├── 03_voice_catalog.py
│   └── 04_custom_device.py
├── device.json.example          # Sample device profile JSON file
├── Voice.json                   # Voice library catalog
└── pyproject.toml               # PEP 517 build configuration
```

---

## Tiếng Việt Documentation

### Donate / Ủng hộ

Nếu project hữu ích cho công việc của bạn, có thể ủng hộ phát triển qua USDT mạng TRC20:

```text
TL4sPkfSTVnmneKvvuCfa2wSDnADjxDqYV
```
Network: **TRC20**

---

### Tính Năng Nổi Bật

- **Package Python Module Chuẩn**: Tên package `capcut-tts-api` (Import `capcut_tts_api`).
- **Tự động liên kết `voice_type` và `resource_id`**: Bạn chỉ cần truyền `voice_type` (ví dụ: `"BV421_vivn_streaming"`), SDK sẽ tự động khớp và điền `resource_id` (`"7252594014782755330"`) từ thư viện `Voice.json`.
- **Python SDK hoàn chỉnh (`capcut_tts_api`)**: Thiết kế dạng module đối tượng (OOP) chuyên nghiệp.
- **Command Line Interface (`capcut-tts-api` CLI)**: Giao diện dòng lệnh qua lệnh `capcut-tts-api` hoặc `python -m capcut_tts_api.cli`.
- **Thuần Python 100%**: Mã hoá RSA PKCS#1 v1.5 và chữ ký AWS SigV4 chạy thuần bằng thư viện chuẩn của Python.

---

### Hướng Dẫn Cài Đặt

Yêu cầu Python 3.9 trở lên.

```bash
# Cài đặt module python vào môi trường
python3 -m pip install -e .

# Hoặc cài thư viện phụ thuộc
python3 -m pip install requests
```

---

### Hướng Dẫn Sử Dụng Python SDK

#### 1. Chuyển Đổi Văn Bản Thành Giọng Nói (TTS)

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# Truyền voice_type (tự động khớp resource_id="7252594014782755330")
result = client.generate_speech(
    texts="Xin chào bạn! Chúc bạn một ngày tốt lành.",
    voice="BV421_vivn_streaming", # voice_type trong Voice.json
    rate="1.0",
    wait=True
)

print(result)
```

---

#### 2. Nhận Diện Phụ Đề Từ File Âm Thanh/Video (STT)

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# Upload file, tạo task STT và lấy phụ đề tự động
res = client.transcribe_file(
    file_path="bai_hat.mp3",
    language="vi-VN",
    wait=True
)

# Trích xuất danh sách phụ đề có mốc thời gian
subtitles = client.extract_subtitles(res)

print("Văn bản toàn bộ:", subtitles.full_text)
for item in subtitles.utterances:
    print(f"[{item.start_time}ms -> {item.end_time}ms] {item.text}")
```

---

#### 3. Tra Cứu Danh Sách Giọng Đọc (Voice Catalog)

```python
from capcut_tts_api import CapCutClient

client = CapCutClient()

# Lấy danh sách các giọng đọc Tiếng Việt
voices = client.list_voices(lang="vi-VN")

for v in voices:
    print(f"{v.display_name} ({v.voice_type}) -> Resource ID: {v.resource_id}")
```

---

### Hướng Dẫn Dòng Lệnh (CLI)

#### 1. Xem danh sách giọng đọc

```bash
capcut-tts-api list-voices --language vi-VN
# Hoặc: python -m capcut_tts_api.cli list-voices --language vi-VN
```

#### 2. Tạo task TTS (Tự động tra cứu resource_id từ voice_type)

```bash
capcut-tts-api tts-new \
  --text "Xin chào thế giới" \
  --voice "BV421_vivn_streaming"
```

#### 3. Upload file và tạo task STT tự động

```bash
capcut-tts-api stt-file \
  --audio-file 1.mp4 \
  --language vi-VN \
  --out response.json
```
