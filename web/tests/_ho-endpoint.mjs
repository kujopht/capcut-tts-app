/*
 * MOT danh sach ho tai nguyen API, dung chung cho moi bai test chot no.
 *
 * VI SAO TON TAI TEP NAY: cung mot danh sach tung duoc chep tay o BON bai test
 * (`ui`, `correctness-scale`, `final-polish`, `m3-m4`). Them mot ho endpoint
 * lam do bon cho, va nguoi sua phai tim ra ca bon — lan nay tim duoc, nhung do
 * la nho bo test chay het chu khong nho ai nho ra.
 *
 * Bon ban sao cua mot su that la bon cho co the lech. Mot ban thi khong.
 *
 * Danh sach nay KHONG cam them ho moi. No bat MOI lan them phai di qua day: mot
 * ho tai nguyen moi la mot be mat API moi, va no phai duoc ai do CO Y viet vao
 * day chu khong tu xuat hien.
 */

import assert from "node:assert/strict";

/** Ho tai nguyen duoi `/api/`, theo thu tu chu cai. */
export const HO_ENDPOINT = [
  // `/api/account/social` — tom tat xa hoi CUA CHINH MINH. Ho rieng chu khong
  // nam duoi `/api/users/{id}/...`: duong nay khong nhan id nao ca, nguoi goi
  // luon la chu token. Mot duong co id la mot duong ai do se thu doi id.
  "account",
  "admin",
  // Animation (overnight Phase 5, V6) — san pham XEM, DOC LAP voi
  // novels/chapters, tren kho rieng `animation_store`. Xem
  // `server/animation_domain.py`.
  "animation",
  "audio",
  "auth",
  "chapters",
  // --- tang xa hoi ---
  "comments",
  "creator",
  "feed",
  "health",
  // Image Studio V1 (overnight build) — Quick Free/Fanfic Credits/My
  // Pollinations, doc lap voi moi ho khac. Xem
  // `docs/reports/image-studio-v1-summary.md`.
  "image",
  // Authorized Import — nhap tep do tac gia/nguoi duoc cho phep tai len.
  // Ho rieng vi body la du lieu nguon + tu khai quyen, khong phai CRUD Novel.
  "import",
  "jobs",
  // Bang xep hang XP (V6 gamification) — CONG KHAI, khong nam duoi
  // `/api/account/...` vi khong doi hoi dang nhap (nguoi xem chua dang nhap
  // van xem duoc, chi thieu `viewer_entry`). Xem
  // `server/gamification_service.py::leaderboard_all_time/leaderboard_weekly`.
  "leaderboard",
  // Gioi han do MAY CHU quyet dinh, cho giao dien noi truoc. Xem
  // `server/social.py::mo_ta_gioi_han`.
  "limits",
  "listens",
  "notifications",
  "novels",
  "posts",
  // V4 visual completion, Phan B — con tro CA NHAN "tiep tuc doc/nghe". Ho
  // RIENG voi `listens` co y: `listens` la UY TIN CONG KHAI cua tac gia,
  // con day la tien ich rieng tu, khac hoan toan quy tac va doi tuong doc.
  "progress",
  "reports",
  "search",
  // Subtitle Studio (overnight Phase 4, V6) — cong cu CUC BO, dich tung dong
  // qua registry chung nhung KHONG tao TranslationProject/job rieng, nen ho
  // rieng thay vi nam duoi `/api/translate/...`.
  "tools",
  // V5 — Novel Translation Studio. Ho RIENG: subsystem khong dung chung bang
  // voi tts_jobs/novels, xem `server/translation_service.py`.
  "translate",
  "users",
  "voices",
];

/** Lay cac ho tai nguyen that su xuat hien trong `lib/api.ts`. */
export function hoTrongApi(apiSrc) {
  return [
    ...new Set([...apiSrc.matchAll(/\/api\/([a-z]+)/g)].map((m) => m[1])),
  ].sort();
}

/** Doi soat, kem thong bao noi ro ho nao vua duoc them hay bo. */
export function kiemHoEndpoint(apiSrc) {
  const co = hoTrongApi(apiSrc);
  const moi = co.filter((h) => !HO_ENDPOINT.includes(h));
  const mat = HO_ENDPOINT.filter((h) => !co.includes(h));
  assert.deepEqual(
    co,
    HO_ENDPOINT,
    `họ endpoint đã đổi. Mới: [${moi}] · Mất: [${mat}]. ` +
      "Nếu đây là điều bạn muốn, hãy sửa tests/_ho-endpoint.mjs.",
  );
}
