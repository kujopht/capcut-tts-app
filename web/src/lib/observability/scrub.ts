/**
 * Làm sạch sự kiện Sentry phía TRÌNH DUYỆT — hàm THUẦN (không import gì), chạy được thẳng
 * trong test Node. Cùng quy tắc với `server/observability.py`:
 *
 *   * KHÔNG query string / fragment / userinfo của MỌI URL (trang, breadcrumb, frame) — mã OAuth
 *     `?code=`, URL ký R2 (`X-Amz-Signature`), token trên link;
 *   * KHÔNG header nào ngoài danh sách cho phép (Referer mang nguyên URL cũ → bỏ);
 *   * KHÔNG Bearer/JWT/khoá Appwrite/Tencent UserSig/cặp `key=value` bí mật/email trong chuỗi;
 *   * KHÔNG `user.email`/`user.ip_address`; khoá bí mật theo TÊN bị thay cả giá trị.
 *
 * Làm sạch hỏng thì BỎ sự kiện (trả `null`), không bao giờ gửi bản thô.
 */

export const AN = "<redacted>";

const TEN_NHAY_CAM = new Set([
  "authorization", "auth", "cookie", "cookies", "set-cookie", "password", "secret", "client_secret", "token",
  "access_token", "refresh_token", "id_token", "api_key", "apikey", "x-appwrite-key", "x-appwrite-session",
  "x-appwrite-jwt", "x-support-session", "usersig", "user_sig", "sdksecretkey", "secret_key", "session",
  "session_id", "jwt", "signature", "private_key", "code_verifier",
]);

const HEADER_CHO_PHEP = new Set(["user-agent", "accept-language", "content-type"]);

const MAU: Array<[RegExp, string]> = [
  [/\b(?:standard|console)_[a-f0-9]{40,}\b/gi, AN],
  [/\bBearer\s+[A-Za-z0-9_\-.~+/]{8,}=*/gi, `Bearer ${AN}`],
  [/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*/g, AN],
  [/(https?:\/\/[^\s?#"'<>]+)[?#][^\s"'<>]*/g, `$1?${AN}`],
  [/\b(X-Amz-(?:Signature|Credential|Security-Token))=[^\s&"'<>]+/gi, `$1=${AN}`],
  [/\beJ[wyz][A-Za-z0-9*_\-=+/]{20,}/g, AN],
  [/\b(user_?sig)\s*[=:]\s*[^\s&"',;]+/gi, `$1=${AN}`],
  [/\b((?:[a-z_]*_)?(?:api[_-]?key|secret|token|password|passwd|signature|credential))(\s*[=:]\s*)[^\s&"',;]{4,}/gi, `$1$2${AN}`],
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "<email>"],
];

export function locChuoi(s: string): string {
  let ra = String(s);
  for (const [mau, thay] of MAU) ra = ra.replace(mau, thay);
  return ra;
}

/** Giữ scheme + host + path; bỏ userinfo, query, fragment. Không phải URL tuyệt đối → lọc như chuỗi. */
export function locUrl(u: unknown): unknown {
  if (typeof u !== "string" || !u) return u;
  try {
    const x = new URL(u);
    return `${x.protocol}//${x.host}${x.pathname}`;
  } catch {
    return locChuoi(u.split(/[?#]/, 1)[0]);
  }
}

export function locDeQui(x: unknown, sau = 8): unknown {
  if (sau <= 0) return AN;
  if (Array.isArray(x)) return x.map((v) => locDeQui(v, sau - 1));
  if (x && typeof x === "object") {
    const ra: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(x as Record<string, unknown>)) {
      ra[k] = TEN_NHAY_CAM.has(k.trim().toLowerCase()) ? AN : locDeQui(v, sau - 1);
    }
    return ra;
  }
  if (typeof x === "string") return locChuoi(x);
  return x;
}

// Sự kiện Sentry là JSON tự do (nhiều phiên bản SDK khác hình dạng) — hàm lọc đi phòng thủ từng khoá.
type BatKy = Record<string, any>;

function lamSachFrame(f: BatKy): void {
  delete f.vars;
  for (const k of ["filename", "abs_path"]) if (typeof f[k] === "string") f[k] = locUrl(f[k]);
  if (typeof f.context_line === "string") f.context_line = locChuoi(f.context_line);
  for (const k of ["pre_context", "post_context"]) {
    if (Array.isArray(f[k])) f[k] = f[k].map((d: unknown) => (typeof d === "string" ? locChuoi(d) : d));
  }
}

export function lamSachBreadcrumb<T extends BatKy | null | undefined>(b: T): T | null {
  try {
    if (!b || typeof b !== "object") return null;
    if (typeof b.message === "string") b.message = locChuoi(b.message);
    if (b.data && typeof b.data === "object") {
      const d = locDeQui(b.data) as BatKy;
      for (const k of ["url", "to", "from"]) if (typeof d[k] === "string") d[k] = locUrl(d[k]);
      b.data = d;
    }
    return b;
  } catch {
    return null;
  }
}

export function lamSachSuKien<T extends BatKy | null | undefined>(ev: T): T | null {
  try {
    if (!ev || typeof ev !== "object") return null;
    const req = ev.request;
    if (req && typeof req === "object") {
      delete req.cookies;
      delete req.data;
      delete req.env;
      if (req.query_string) req.query_string = AN;
      if ("url" in req) req.url = locUrl(req.url);
      if (req.headers && typeof req.headers === "object") {
        const h: BatKy = {};
        for (const [k, v] of Object.entries(req.headers as BatKy)) {
          if (HEADER_CHO_PHEP.has(k.toLowerCase())) h[k] = typeof v === "string" ? locChuoi(v) : v;
        }
        req.headers = h;
      }
    }
    if (ev.user && typeof ev.user === "object") ev.user = {};
    for (const ex of ev.exception?.values ?? []) {
      if (typeof ex.value === "string") ex.value = locChuoi(ex.value);
      for (const f of ex.stacktrace?.frames ?? []) lamSachFrame(f);
    }
    if (typeof ev.message === "string") ev.message = locChuoi(ev.message);
    if (Array.isArray(ev.breadcrumbs)) ev.breadcrumbs = ev.breadcrumbs.map((b: BatKy) => lamSachBreadcrumb(b)).filter(Boolean);
    for (const k of ["extra", "contexts", "tags"]) if (ev[k]) ev[k] = locDeQui(ev[k]);
    if (typeof ev.transaction === "string") ev.transaction = String(locUrl(ev.transaction));
    return ev;
  } catch {
    return null;
  }
}
