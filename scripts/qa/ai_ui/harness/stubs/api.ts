/**
 * Thay `@/lib/api` trong harness QA: chỉ giữ ba thứ mà `lib/ai/client.ts` dùng (API_BASE, ApiError, getToken).
 * Token vẫn nằm ở localStorage `fas.token` giống bản thật, nên "đăng nhập" trong harness = đặt token.
 */
export const API_BASE = "http://qa.local";

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const TOKEN_KEY = "fas.token";

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // bỏ qua
  }
}
