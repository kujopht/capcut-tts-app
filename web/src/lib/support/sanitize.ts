/**
 * Làm sạch PHÍA CLIENT trước khi gửi bất cứ thứ gì cho Fanfic AI Support.
 *
 * Máy chủ làm sạch LẠI (`server/support/sanitize.py`) — không bao giờ tin
 * client. Lớp này tồn tại để thứ nhạy cảm KHÔNG rời trình duyệt ngay từ đầu:
 * token trong URL, URL ký (`X-Amz-*`), email, JWT, UserSig.
 */

const DA_CHE = "[đã che]";

export function sachChuoi(s: unknown, toiDa = 500): string {
  if (s == null) return "";
  let t = String(s).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, " ");
  // URL: giữ scheme + host + đường dẫn; BỎ user:pass@, query và fragment.
  t = t.replace(/\b(https?:\/\/)(?:[^\s/@]+@)?([^\s/?#]+)([^\s?#]*)(?:[?#][^\s]*)?/gi, "$1$2$3");
  t = t.replace(/\bbearer\s+[A-Za-z0-9._~+/=-]{6,}/gi, `Bearer ${DA_CHE}`);
  t = t.replace(/\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]+)?/g, DA_CHE);
  t = t.replace(
    /\b(api[_-]?key|apikey|secret(?:[_-]?key)?|access[_-]?token|refresh[_-]?token|token|password|passwd|pwd|sig|signature|user[_-]?sig|x-amz-[a-z-]+|authorization|cookie|session(?:[_-]?id)?|credentials?)(\s*[=:]\s*)("[^"]*"|'[^']*'|[^\s,;&]+)/gi,
    `$1$2${DA_CHE}`,
  );
  t = t.replace(/\b[0-9a-fA-F]{32,}\b/g, DA_CHE);
  t = t.replace(/\b(?=[A-Za-z0-9+_-]*\d)(?=[A-Za-z0-9+_-]*[A-Z])(?=[A-Za-z0-9+_-]*[a-z])[A-Za-z0-9+_-]{32,}={0,2}/g, DA_CHE);
  t = t.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, "[email]");
  t = t.replace(/\s+/g, " ").trim();
  return t.slice(0, toiDa);
}

/** CHỈ pathname — không query (token, `?c=` của tin nhắn…), không hash. */
export function duongDanAnToan(p: string | null | undefined): string {
  const s = String(p ?? "").split("?")[0].split("#")[0];
  return s.startsWith("/") && s.length <= 300 ? s : "/";
}

export function maLoi(s: unknown): string {
  const v = String(s ?? "").trim().toLowerCase();
  return /^[a-z0-9_.-]{1,48}$/.test(v) ? v : "";
}
