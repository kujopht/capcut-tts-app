# Object mồ côi trong `fanfic-prod` từ lần chạy cổng Cloud Run — 2026-09-06

**Trạng thái: CHƯA XOÁ. Ghi lại để dọn có kiểm chứng về sau.**

## Chuyện gì đã xảy ra

Ngày 2026-09-06, khi chuẩn bị cổng nghiệm thu cho Cloud Run job `tts-worker`,
10 job thử nghiệm được tạo với ý định chạy trên hạ tầng staging. Chúng lại rơi
vào **kho metadata production**, vì job Cloud Run được cấu hình:

| Hạng mục | Toạ độ production (`scripts/ops/cutover_target.py:37-41`) | Cloud Run `tts-worker` |
|---|---|---|
| `APPWRITE_ENDPOINT` | `https://appwrite-dev.fanfic.world/v1` | giống hệt |
| `APPWRITE_PROJECT_ID` | `fanfic-world-prod` | giống hệt |
| `APPWRITE_DATABASE_ID` | `fanfic_world_prod` | giống hệt |
| `R2_BUCKET` | `fanfic-prod` | `fanfic-staging` |

Bucket riêng **không phải** là cách ly: hàng đợi quyết định ai làm việc. Worker
AWS production (`fanfic-worker-prod.service`, host `13.212.224.218`) giành cả 10
job trong ~2 giây sau khi tạo — trước cả khi Cloud Run kịp khởi động:

```
job tạo    04:02:48 – 04:02:59 UTC
job chạy   04:02:50 – 04:03:02 UTC   <- worker AWS production
Cloud Run khởi động   04:03:39 UTC   <- muộn hơn, không giành được job nào
```

Worker AWS ghi audio vào bucket của chính nó — `fanfic-prod`. Toàn bộ metadata
(4 tài khoản, 4 truyện, 10 chương, 10 job, 10 track) đã được xoá sạch bằng đúng
đường `AccountDeletionService.delete_account`, và CSDL đã trở về đúng trạng thái
nền (306 completed / 13 failed / 0 pending / 0 running). Còn lại là các object
trong `fanfic-prod` mà đường xoá đó **không** với tới được: khoá R2 đang dùng bị
giới hạn phạm vi ở `fanfic-staging`, nên `_xoa_doi_tuong` trả về `objects: 0`.

## 20 khoá cần dọn

Đây là giá trị **đã ghi trong `tts_jobs.output_key` và `audio_tracks.transcript_key`**
đọc ra trước khi xoá metadata — không phải suy đoán. Nhưng **sự tồn tại của chúng
trong `fanfic-prod` chưa được kiểm chứng**, vì phiên làm việc không có khoá đọc
bucket đó. Đó chính là lý do bước dọn phải "có kiểm chứng".

Bucket: `fanfic-prod`. Run id fixture: `3f800ba0`. Tài khoản đã tạo ra chúng:
`crgate-3f800ba0-u1..u4@fanfic.invalid` (đã xoá).

```
audio/6a9ce5e5cdefe36ef675/chp_3545abc25e9e4dc5/8a20e63959d8670d1fc3551465335a185be70260f65e4c13175deee729d2604d.mp3
audio/6a9ce5e5cdefe36ef675/chp_3545abc25e9e4dc5/8a20e63959d8670d1fc3551465335a185be70260f65e4c13175deee729d2604d.transcript.json
audio/6a9ce5e5cdefe36ef675/chp_3d2e21ca24b84f83/836be7e0545c50a3b60070575a1cf6e7e6be3d549b8c17a4312f6ffdfbc5823a.mp3
audio/6a9ce5e5cdefe36ef675/chp_3d2e21ca24b84f83/836be7e0545c50a3b60070575a1cf6e7e6be3d549b8c17a4312f6ffdfbc5823a.transcript.json
audio/6a9ce5e5cdefe36ef675/chp_e6f80257ac564262/4d70b860d2f46e47b9bbc5c759865149e65a0e606226a324573b00267b7310c2.mp3
audio/6a9ce5e5cdefe36ef675/chp_e6f80257ac564262/4d70b860d2f46e47b9bbc5c759865149e65a0e606226a324573b00267b7310c2.transcript.json
audio/6a9ce5ec00ae8246f759/chp_557daa3f22a34ea6/06ad47268370c7f7b01a9c9e4c4a694fad7640dca0d1ebc779b8d4ae56e7d814.mp3
audio/6a9ce5ec00ae8246f759/chp_557daa3f22a34ea6/06ad47268370c7f7b01a9c9e4c4a694fad7640dca0d1ebc779b8d4ae56e7d814.transcript.json
audio/6a9ce5ec00ae8246f759/chp_acee75ddfa224c36/f21ce33cf7c516d6674b351f79f44bace53ab7868146b3f07ec56f0618e2075a.mp3
audio/6a9ce5ec00ae8246f759/chp_acee75ddfa224c36/f21ce33cf7c516d6674b351f79f44bace53ab7868146b3f07ec56f0618e2075a.transcript.json
audio/6a9ce5ec00ae8246f759/chp_4cde1f2853a74f0d/2996002b78fe66e3462c6c712cb5358e9945e447c43b5aa15f6b0bdddd13bfcd.mp3
audio/6a9ce5ec00ae8246f759/chp_4cde1f2853a74f0d/2996002b78fe66e3462c6c712cb5358e9945e447c43b5aa15f6b0bdddd13bfcd.transcript.json
audio/6a9ce5efa441dff0e3cd/chp_f788dfedff51484e/133a78833ae5e1650bacd35b5a80ebd7d12c6b43e905e4c0d523f65b28411de0.mp3
audio/6a9ce5efa441dff0e3cd/chp_f788dfedff51484e/133a78833ae5e1650bacd35b5a80ebd7d12c6b43e905e4c0d523f65b28411de0.transcript.json
audio/6a9ce5efa441dff0e3cd/chp_1f852199b3804c42/6ac24fca048129f3ea17c222cc77a60e272c56ec22d6bebfa29acee5b1cfd094.mp3
audio/6a9ce5efa441dff0e3cd/chp_1f852199b3804c42/6ac24fca048129f3ea17c222cc77a60e272c56ec22d6bebfa29acee5b1cfd094.transcript.json
audio/6a9ce5efa441dff0e3cd/chp_dfd7b693974d4079/88cf05a5087348699ebe5a7f226c94917daea8e07c38695d36740a4d4d0db650.mp3
audio/6a9ce5efa441dff0e3cd/chp_dfd7b693974d4079/88cf05a5087348699ebe5a7f226c94917daea8e07c38695d36740a4d4d0db650.transcript.json
audio/6a9ce5f312036e164450/chp_a22ebb7584374a5c/d66d7a48fb41bca19b10dbd0210d5e231feeb8257ab217d96f4db0976d0d1aae.mp3
audio/6a9ce5f312036e164450/chp_a22ebb7584374a5c/d66d7a48fb41bca19b10dbd0210d5e231feeb8257ab217d96f4db0976d0d1aae.transcript.json
```

## Mức độ cấp bách: thấp

Metadata trỏ tới chúng đã bị xoá, nên **không route nào chạm tới được** — cùng
kết luận đã ghi trong `docs/HANDOFF.md` mục "Xử lý mồ côi". Tổng dung lượng ước
tính vài trăm KB. Đây là rác, không phải lỗ hổng.

## Quy trình dọn có kiểm chứng (khi có khoá phạm vi `fanfic-prod`)

Theo đúng bốn điều kiện tối thiểu mà `docs/HANDOFF.md` đã đặt ra cho bất kỳ bản
tự xoá nào:

1. **`HEAD` từng khoá trước.** Khoá nào không tồn tại thì bỏ qua và ghi lại —
   không coi là lỗi. Danh sách trên là *ghi nhận từ metadata*, chưa xác nhận
   phía R2.
2. **Đối chiếu ngược:** với mỗi khoá còn tồn tại, xác nhận **không** có
   `audio_tracks` nào trong `fanfic_world_prod` trỏ vào nó. Bốn tài khoản
   `crgate-*` đã bị xoá nên điều này phải đúng — nhưng phải *đo*, không phải
   *tin*. Một khoá còn track trỏ tới nghĩa là danh sách này sai, phải dừng.
3. **Chạy `--dry-run` trước**, in ra đúng những gì sẽ xoá.
4. **Chỉ xoá 20 khoá trong danh sách này**, khớp chuỗi chính xác. Không dùng
   tiền tố, không dùng wildcard: tiền tố `audio/6a9ce5...` là `owner_id`, và
   một lỗi đánh máy trong wildcard sẽ chạm vào dữ liệu người dùng thật.

Không bao giờ xoá bằng cách quét toàn bucket rồi suy ra "cái nào mồ côi" — đó là
race đã được phân tích và bác bỏ trong `docs/HANDOFF.md`.

## Việc phải làm trước, quan trọng hơn dọn rác

Cấu hình lệch của job `tts-worker` vẫn còn nguyên: nó vẫn trỏ vào
`fanfic_world_prod`. Chừng nào chưa sửa, mỗi lần job đó chạy là một lần nó có
thể giành một job production thật rồi ghi audio vào `fanfic-staging`, để lại một
`audio_track` trỏ vào object mà đường đọc production không phân giải được —
tức là một trình phát hỏng câm lặng cho người dùng thật. Cả hai execution đã bị
cancel ngày 2026-09-06; **đừng chạy lại job này trước khi sửa toạ độ.**
