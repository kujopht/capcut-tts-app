/**
 * Thay `@/lib/session` trong harness QA: hồ sơ do trang QA điều khiển (`__qa.setUser`), để thử chuyển tài khoản
 * (đăng xuất / đăng nhập người khác) TRONG CÙNG một trang — đúng điều SessionProvider thật làm (không tải lại trang).
 */
import { useSyncExternalStore } from "react";

export interface Profile {
  user_id: string;
  email: string;
  display_name: string;
  tier: string;
}

let current: Profile | null = null;
const listeners = new Set<() => void>();

export function qaSetProfile(p: Profile | null): void {
  current = p;
  listeners.forEach((f) => f());
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useSession() {
  const profile = useSyncExternalStore(subscribe, () => current, () => null);
  return {
    profile,
    loading: false,
    signIn: async () => {},
    signUp: async () => {},
    signOut: async () => qaSetProfile(null),
    adoptSession: () => {},
    updateProfile: () => {},
  };
}
