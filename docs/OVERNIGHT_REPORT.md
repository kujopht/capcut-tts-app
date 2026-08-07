# Overnight verification — 2026-08-07

Chạy tự động trên môi trường **development**: Appwrite Cloud 1.9.6 (region `sgp`)
+ Cloudflare R2 (bucket private `fanfic`).

| | |
|---|---|
| Branch | `feature/web-mvp` |
| Commit khi bắt đầu | `c6fbe9462d6bb8fd013ec09a29e0223c16723d2a` — *Verify live Appwrite and R2 integration* |
| Working tree khi bắt đầu | Sạch |
| **Lỗi tìm thấy** | **Không có** |
| **Code đã sửa** | **Không** |
| Kết quả live | **36/36 kiểm tra đạt** |

Tài liệu này không chứa credential, token, session hay presigned URL đầy đủ.

---

## 1. Kiểm tra offline

| Kiểm tra | Kết quả | Exit |
|---|---|---|
| Backend tests (`server/tests`) | 182 test — 181 đạt, 1 bỏ qua | 0 |
| Backend tests trong **venv sạch** cài từ `server/requirements.txt` | 181 đạt, 1 bỏ qua | 0 |
| `npx eslint .` | Sạch | 0 |
| `npx tsc --noEmit` | Sạch | 0 |
| Web tests (`node --test`) | 10/10 đạt | 0 |
| `npx next build` | Thành công, 7 route | 0 |

Test bỏ qua là test kiểm tra thông báo lỗi *khi thiếu `boto3`*; `boto3` đã nằm
trong `server/requirements.txt` nên nó tự bỏ qua — đúng thiết kế.

---

## 2. Kiểm tra live — 36/36 đạt

### 2.1 Môi trường (2/2)

`/api/health` trả `data_backend: appwrite`, `storage_backend: r2`,
`env_file_loaded: true`. Phản hồi không chứa mảnh secret nào.

### 2.2 Xác thực (1/1)

Đăng ký tài khoản thử → `GET /api/auth/me` trả đúng danh tính.

### 2.3 Bốn job TTS ngắn song song (6/6)

Nội dung **28 / 35 / 30 / 29 ký tự** — mỗi chương một câu. Không dùng nội dung dài.

| Kiểm tra | Kết quả |
|---|---|
| Mỗi job một `job_id` riêng | ✅ |
| Không job nào bị báo nhầm là `reused` | ✅ |
| Cả 4 kết thúc | ✅ 78,9 giây |
| Cả 4 thành công | ✅ 4/4 |
| Không tự đổi sang giọng khác | ✅ |
| Mỗi job một `output_key` riêng | ✅ |

### 2.4 Đối chiếu metadata Appwrite ↔ object R2 (3/3)

Với **từng** chương: `audio_track` tồn tại · object có trên R2 ·
`size_bytes` trong Appwrite **khớp** `ContentLength` trên R2 ·
`Content-Type` là `audio/mpeg` · `object_key` chứa đúng `chapter_id` của nó.

Kích thước: **15.120 / 17.280 / 15.120 / 16.416 byte** — khác nhau đúng như nội
dung khác nhau, chứng tỏ không lẫn audio giữa các chương.

### 2.5 Presigned URL và private access (9/9)

| Kiểm tra | Kết quả |
|---|---|
| Chủ sở hữu nhận `307` | ✅ |
| URL có `X-Amz-Signature` và `X-Amz-Expires=300` | ✅ |
| Tải được qua URL ký | ✅ 15.120 byte |
| `Content-Type` khi tải về | ✅ `audio/mpeg` |
| Là MP3 hợp lệ | ✅ |
| **URL công khai cố định bị chặn** | ✅ |
| URL ký còn hạn tải được | ✅ |
| **URL ký hết hạn bị từ chối** | ✅ HTTP 403 |
| Chương nháp: ẩn danh bị chặn | ✅ HTTP 401 |

### 2.6 Lỗi và retry (7/7)

Gửi job với `voice_id` không tồn tại:

| Kiểm tra | Kết quả |
|---|---|
| Job chuyển `failed` | ✅ |
| Có `error_kind` và `error_message` | ✅ `error_kind: voice_not_found` |
| **Không tự đổi sang giọng khác** | ✅ giữ nguyên voice_id đã yêu cầu |
| Job `failed` không có `output_key` | ✅ |
| Không tạo `audio_track` khi thất bại | ✅ |
| Job `failed` **không** bị tái dùng khi gửi lại | ✅ tạo job mới |
| Retry bằng giọng hợp lệ → `completed` | ✅ |

### 2.7 Mồ côi (3/3) — chỉ đo, không xoá dữ liệu có trước

Tại đỉnh điểm: **11 object trên R2, 11 `audio_track` trong Appwrite**.

| Kiểm tra | Kết quả |
|---|---|
| Object mồ côi (có file, không metadata) | ✅ **0** |
| Metadata mồ côi (có metadata, không file) | ✅ **0** |
| Job kẹt ở trạng thái `running` | ✅ **0** |

Vận hành bình thường không sinh rác ở cả hai chiều.

### 2.8 Dọn dẹp (5/5)

| Kiểm tra | Kết quả |
|---|---|
| Mọi object của lượt chạy này đã biến mất | ✅ |
| **Không đụng vào object có sẵn** | ✅ nền 6 → còn 6 |
| Không còn document thừa nào | ✅ 0 ở cả 5 collection |
| **Không xoá nhầm document có sẵn** | ✅ tập nền vẫn là tập con của tập cuối |
| Sau dọn dẹp vẫn nhất quán | ✅ 6 object ↔ 6 track, không sinh mồ côi |

---

## 3. Cloud resource đã tạo và xoá

Ảnh nền chụp **trước** khi chạy: 6 object trên R2; Appwrite có 11 novels,
12 chapters, 7 tts_jobs, 6 audio_tracks, 11 profiles.

| Loại | Đã tạo | Đã xoá |
|---|---|---|
| Tài khoản thử (user + profile) | 1 | 1 |
| Novel | 1 | 1 |
| Chapter | 5 | 5 |
| TTS job | 7 | 7 |
| Audio track (metadata) | 5 | 5 |
| Object trên R2 | 5 | 5 |

Xoá **cả metadata lẫn object**, theo thứ tự `audio_tracks` → object R2 → `tts_jobs`
→ `chapters` → `novels` → `profiles` + user, nên không để lại trạng thái nửa vời.

Bộ lọc an toàn: bất kỳ key nào có trong ảnh nền đều **bị bỏ qua** khi xoá, nên
không thể chạm vào dữ liệu có trước. Đã kiểm chứng bằng cách so tập nền với tập
cuối ở cả R2 lẫn cả 5 collection.

Trạng thái cuối trùng khớp ảnh nền: **6 object, 6 audio_track, 0 mồ côi**.

7 job đã xoá gồm 4 job song song, 1 job hỏng có chủ ý, 1 job retry cùng giọng
hỏng, và 1 job retry bằng giọng hợp lệ.

---

## 4. Lỗi tìm thấy

**Không có.** Không kiểm tra nào thất bại, nên **không sửa dòng code nào** và
không có commit sửa lỗi.

Một hành vi đã biết, không phải lỗi mới, đã ghi từ lượt trước: khi metadata trỏ
tới object không tồn tại, backend vẫn trả `307` tới URL ký và R2 trả `404` —
backend không kiểm tra tồn tại trước khi chuyển hướng. Phân quyền vẫn đúng.
Lượt này **không tái hiện được** trong vận hành bình thường (0 metadata mồ côi).
Ba phương án xử lý đã nêu trong `docs/HANDOFF.md`; cần bạn chọn.

---

## 5. Commit và git status

Không có thay đổi code. Commit duy nhất của lượt này là chính tài liệu báo cáo.

`git status` cuối: **sạch**.

Không push, không deploy, không build installer, không amend.

---

## 6. Blocker

**Không có.** Không gặp lỗi permission, credential hay quota. Không mở rộng
quyền và không thay đổi cấu hình cloud nào.

Ghi chú vận hành: quota Appwrite Cloud và R2 gần như không suy suyển — bốn câu
ngắn, tổng khoảng 64 KB audio, và toàn bộ đã được xoá lại.

---

## 7. Việc thủ công còn lại

Backend (`:8000`) và web (`:3000`) vẫn đang chạy ở chế độ Appwrite + R2.

Luồng cần bấm tay trên trình duyệt — chưa tự động hoá được:

1. `/login` — đăng ký (mật khẩu **≥ 8 ký tự**), đăng xuất, đăng nhập lại.
2. `/studio` — tạo truyện tiêu đề tiếng Việt có dấu, thêm chương 300–800 chữ.
3. Chọn giọng **Hoài My** (`edge:vi-VN-HoaiMyNeural`), gửi job, xem trạng thái
   tự nhảy `pending` → `running` → `completed`.
4. Bấm phát trên trang chương; tải MP3 bằng chuột phải → *Save audio as…*
5. Mở **cửa sổ ẩn danh**, dán link chương → phải **bị chặn** khi chưa xuất bản.
6. Xuất bản truyện → `/library` hiện truyện → cửa sổ ẩn danh giờ **nghe được**.

Ngoài ra vẫn chưa kiểm chứng:

- Chương dài chạm giới hạn 1.000.000 ký tự của thuộc tính `content`
  (lượt này cố ý dùng nội dung ngắn).
- Tải cao hơn 4–5 job song song.
- Giọng Piper cục bộ qua backend web (vẫn `commercial_ready: false`).
- Cấu hình production: CORS thật, domain thật, ký số cho desktop.
- Job quét dọn object mồ côi — chưa viết.

Việc nên làm lúc rảnh: token R2 cũ và Appwrite API key đã từng xuất hiện trong
hội thoại. Thu hồi ở **R2 → Manage API Tokens** và **Appwrite → Integrations →
API Keys**, tạo mới rồi nhập bằng `Set-EnvSecret`.
