/**
 * GOI THOAI / VIDEO — CHUA hien thuc (du dinh: Tencent TRTC). Chi khai bao hop dong de nut goi o dau cuoc
 * tro chuyen co mot cho doc "da san sang chua", thay vi tu doan.
 *
 * Kien truc du kien (KHONG nam trong PR nay):
 *   - May chu cap `UserSig` TRTC ngan han qua `POST /api/chat/calls/token` (khoa TRTC CHI o may chu, cung
 *     `fw_<uid>` voi tin nhan — `server/messaging/ids.py`), kiem hai nguoi KHONG chan nhau truoc khi cap.
 *   - Tin hieu moi goi (dang goi / nhan / tu choi) di qua CHINH luong Appwrite cua chat (loai tin "call").
 *   - SDK TRTC tai LUOI (dynamic import) chi khi bam goi — nguoi chi nhan tin chu tai 0 byte TRTC.
 *
 * Cho toi luc do, moi nang luc la `false`: nut goi hien o trang thai "Sắp có", bi vo hieu hoa — khong co
 * hanh dong gia nao.
 */
export type CallKind = "voice" | "video";

export interface CallCapabilities {
  voice: boolean;
  video: boolean;
}

export const CALLS_UNAVAILABLE: CallCapabilities = { voice: false, video: false };

export function callCapabilities(): CallCapabilities {
  return CALLS_UNAVAILABLE;
}
