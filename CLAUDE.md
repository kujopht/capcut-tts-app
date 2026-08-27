# Fanfic Audio Studio

Kho này chứa **hai sản phẩm** dùng chung một pipeline TTS:

| Phần | Vị trí | Trạng thái |
|---|---|---|
| Ứng dụng desktop Windows (PySide6) | `app.py`, `desktop_app/`, `capcut_tts_api/` | Đang chạy ổn định, đã có installer |
| Nền tảng web (Next.js + FastAPI) | `web/`, `server/` | Production (`fanfic.world`) đã deploy — chưa thương mại nhưng LÀ site thật, không phải mặc định coi "chưa deploy". `staging.fanfic.world` ĐÃ RETIRED (2026-08) — không tự ý dựng lại; xem `docs/DEV_PUBLIC_STAGING.md` |

## Quy tắc bắt buộc

- **Không sửa `capcut_tts_api/`** trước khi chứng minh lỗi nằm ở đó. Đây là bản đã kiểm chứng.
- **Backend web không được import GUI.** `server/` chỉ chạm tới `desktop_app.providers.*`, `desktop_app.text_chunker`, `desktop_app.models`, `desktop_app.output_manager` — đã xác minh không kéo theo PySide6.
- **Mọi bí mật chỉ ở backend.** Trình duyệt chỉ biết `NEXT_PUBLIC_API_BASE`.
- **Không tự đổi sang giọng khác** khi tổng hợp thất bại, ở cả desktop lẫn web.
- **Không commit** model `.onnx`, audio, preview cache, `build/`, `dist/`, `installer_output/`, `node_modules/`, `.env`.
- **Mọi báo cáo viết bằng tiếng Việt**, bảng so sánh dùng cột `Hạng mục | Trước khi sửa | Sau khi sửa`.
- Không push GitHub khi chưa được yêu cầu.
- **Deploy web PHẢI dùng đúng lệnh tường minh** (sau sự cố 2026-08-18: một lần
  deploy staging bị đẩy nhầm thẳng lên production do gọi lệnh mơ hồ):
  - **Staging**: worker `fanfic-web-staging`, domain `staging.fanfic.world`,
    cấu hình `web/wrangler.staging.jsonc`, `npm run cf:deploy:staging`. ĐÃ
    RETIRED (2026-08) — KHÔNG chạy lệnh này để tự ý dựng lại staging; giữ
    nguyên cấu hình ở đây chỉ để biết đích cũ nếu cần tra cứu.
  - **Production**: worker `fanfic-web`, domain `fanfic.world`, cấu hình
    `web/wrangler.jsonc`, `npm run cf:deploy:production`.
  - Không có lệnh `cf:deploy` trần — đã bỏ cố ý. Không tự suy ra API base hay
    đích deploy từ tài liệu cũ; luôn đối chiếu `web/wrangler*.jsonc` và domain
    thật (`npx wrangler deployments list --name <worker>`) trước khi deploy.

## Lệnh thường dùng

### Desktop
```bash
.\.venv\Scripts\python.exe -m compileall -q app.py desktop_app tests
QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe -m unittest discover -s tests -t .
.\run_app.bat            # mở app
.\build_app.bat          # build EXE (onedir)
```
Installer: mở `installer.iss` bằng `C:\Users\robux\AppData\Local\Programs\Inno Setup 6\ISCC.exe`.

### Backend web
```bash
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m unittest discover -s server/tests -t .
```
Phụ thuộc backend ở `server/requirements.txt` (tách khỏi `requirements-gui.txt`,
đã gồm `boto3` cho R2). Không cài gói nào bằng tay.

### Web
```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run typecheck
npm run build
npm test
```

## Kiến trúc TTS

Mọi thứ đi qua `desktop_app/providers/registry.py::ProviderRegistry`:

- `capcut` — bọc `desktop_app/tts_service.py` (không đổi hành vi)
- `edge` — `edge-tts`, có thử lại khi dịch vụ trả rỗng
- `piper` — chạy cục bộ, model `.onnx` + `.onnx.json` ở `%LOCALAPPDATA%\FanficAudioStudio\models\piper`

Backend web bọc thêm một lớp mỏng ở `server/tts_bridge.py` — **không sao chép logic**, chỉ gọi lại chunker và registry.

## Đặc thù môi trường máy này

- Smart App Control **đang bật cưỡng chế**. EXE/DLL chưa ký có thể bị Code Integrity chặn ở lần chạy đầu (sự kiện 3033/3077). Ký số là việc sau MVP. **Không tắt Smart App Control** — thao tác này không thể hoàn tác.
- `Documents` bị OneDrive chuyển hướng.
- ffmpeg/ffprobe ở `%LOCALAPPDATA%\Microsoft\WinGet\Links\`.
- Inno Setup nằm ở phạm vi người dùng, không phải `Program Files`.

## AI engineering router (V2)

Chính sách chọn model/effort/subagent/**provider** cho công việc kỹ thuật
trong kho này (Haiku cho tra cứu, Sonnet mặc định, Opus cho việc khó/rủi
ro cao, Fable chỉ dành cho việc CỰC LỚN — cộng thêm từ V2: Google
Antigravity CLI [`agy`, quota Google AI Pro riêng] và Codex CLI làm hai
compute pool ngoài, dùng khi lượng Claude đang căng hoặc cần review độc
lập khác họ model) — xem `docs/AI_ROUTER.md` cho đầy đủ, và
`.claude/agents/` cho các subagent Claude cụ thể (`explorer`,
`test-analyst`, `builder`, `frontend-builder`, `code-reviewer`,
`incident-architect`, `long-horizon-lead`). Không phải một tính năng sản
phẩm. Không lưu credential của Antigravity/Codex trong repo — cả hai đọc
phiên đăng nhập từ nơi lưu trữ riêng của hệ điều hành/CLI.

**Quan hệ với router toàn cục:** `~/.claude/CLAUDE.md` (tài khoản Windows
này) chứa phần CHUNG của chính sách này (tier model chung, quota-aware
routing, review chéo model, chính sách context/test) — áp dụng cho MỌI
repo trên máy này, không riêng Fanfic. File này + `docs/AI_ROUTER.md` chỉ
còn phần THẬT SỰ đặc thù Fanfic (production/Appwrite/nội dung, quy ước
frontend riêng, các con số benchmark của repo này) — Claude Code tự nối
cả hai (global rồi đến local), không cần lặp lại phần chung ở đây. Đừng
đưa quy tắc riêng của Fanfic ngược lên `~/.claude/` — file đó phải luôn
dùng được cho một repo bất kỳ khác.

## Trạng thái

Xem `docs/HANDOFF.md` để biết mốc nào đã xong và việc tiếp theo.
