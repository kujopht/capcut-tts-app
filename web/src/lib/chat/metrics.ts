/**
 * Bo dem CHUNG MINH "lazy login" cua Fanfic Chat V1.
 *
 * Tencent Chat tinh MAU theo lan dang nhap SDK. Mot nguoi chi doc/nghe truyen
 * phai co CA BA con so bang 0. Doc duoc tu hai noi, khong can cong cu gi:
 *
 *   window.__fanficChat                  { sessionRequests, sdkLoads, logins, ... }
 *   <html data-chat-sdk="...">           "idle" | "loading" | "loaded" | "logged-in"
 *
 * Khong gui di dau, khong chua du lieu ca nhan — chi dem va ly do mo.
 */
import type { ChatStatus } from "./types";

export interface ChatMetrics {
  /** So lan goi `POST /api/chat/session`. */
  sessionRequests: number;
  /** So lan `import("@tencentcloud/chat")` thuc su chay. */
  sdkLoads: number;
  /** So lan `chat.login()` thanh cong. */
  logins: number;
  loginFailures: number;
  /** Ly do moi lan khoi tao (vd "inbox", "messages-page", "profile-dm", "resume"). */
  initReasons: string[];
  status: ChatStatus;
}

declare global {
  interface Window {
    __fanficChat?: ChatMetrics;
  }
}

function bang(): ChatMetrics | null {
  if (typeof window === "undefined") return null;
  window.__fanficChat ??= {
    sessionRequests: 0,
    sdkLoads: 0,
    logins: 0,
    loginFailures: 0,
    initReasons: [],
    status: "idle",
  };
  return window.__fanficChat;
}

type Dem = "sessionRequests" | "sdkLoads" | "logins" | "loginFailures";

export function dem(truong: Dem): void {
  const b = bang();
  if (b) b[truong] += 1;
}

export function ghiLyDo(lyDo: string): void {
  bang()?.initReasons.push(lyDo);
}

export function ghiTrangThai(s: ChatStatus): void {
  const b = bang();
  if (b) b.status = s;
}

export function ghiSdk(giaiDoan: "idle" | "loading" | "loaded" | "logged-in"): void {
  if (typeof document !== "undefined") document.documentElement.dataset.chatSdk = giaiDoan;
}
