"use client";

/**
 * Phien dang nhap phia trinh duyet.
 *
 * Token duoc luu o localStorage va gan vao moi request qua `api.ts`.
 * KHONG co bi mat nao o day: token do backend cap, va backend moi la noi
 * giu Appwrite API key / R2 credential.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ApiError, api, getToken, setToken, type Profile } from "./api";

interface SessionValue {
  profile: Profile | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName: string) => Promise<void>;
  /**
   * Nhan mot phien da duoc backend cap san.
   *
   * Dung cho luong OAuth: trang callback doi cap dung-mot-lan lay
   * `{token, profile}` — DUNG hinh dang ma `signIn` nhan duoc — roi giao lai
   * cho day. Khong co he thong phien thu hai, va khong co duong nao khac
   * ghi vao `localStorage`.
   */
  adoptSession: (token: string, profile: Profile) => void;
  /**
   * Bất đồng bộ vì nó phải gọi máy chủ huỷ phiên. Nơi gọi có thể bỏ qua
   * Promise — token phía trình duyệt luôn được xoá, kể cả khi lời gọi hỏng.
   */
  signOut: () => Promise<void>;
  /**
   * Thay hồ sơ đang giữ bằng bản MỚI, không đụng token.
   *
   * Dùng sau các thao tác tự trả về `{ profile }` mới (đổi avatar, username,
   * bio…) — nơi gọi đã CÓ sẵn bản mới trong tay, gọi lại `/api/auth/me` chỉ
   * tốn thêm một round-trip vô ích.
   */
  updateProfile: (next: Profile) => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  // Khoi phuc phien khi tai lai trang
  useEffect(() => {
    let cancelled = false;

    // Truong hop "chua co token" cung phai di qua chuoi bat dong bo, de khong
    // co setState nao nam truc tiep trong than effect.
    const restore = async (): Promise<Profile | null> => {
      if (!getToken()) return null;
      return (await api.me()).profile;
    };

    restore()
      .then((restored) => {
        if (!cancelled && restored) setProfile(restored);
      })
      .catch(() => {
        // Token het han hoac backend chua chay -> coi nhu chua dang nhap
        setToken(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    setToken(result.token);
    setProfile(result.profile);
  }, []);

  const signUp = useCallback(
    async (email: string, password: string, displayName: string) => {
      const result = await api.register(email, password, displayName);
      setToken(result.token);
      setProfile(result.profile);
    },
    [],
  );

  const adoptSession = useCallback((token: string, next: Profile) => {
    setToken(token);
    setProfile(next);
  }, []);

  const signOut = useCallback(async () => {
    // Báo máy chủ huỷ phiên TRƯỚC, vì lời gọi cần chính token sắp bị xoá.
    //
    // Lỗi mạng KHÔNG được giữ người dùng ở trạng thái đã đăng nhập: dọn phía
    // trình duyệt trong `finally` để nút "Đăng xuất" luôn có tác dụng thấy
    // được. Máy chủ hụt một lần huỷ thì phiên vẫn hết hạn theo thời gian.
    try {
      await api.logout();
    } catch {
      // Không có gì hữu ích để nói với người dùng ở đây, và giữ họ đăng nhập
      // vì một lần mạng chập là tệ hơn hẳn.
    } finally {
      setToken(null);
      setProfile(null);
    }
  }, []);

  const value = useMemo<SessionValue>(
    () => ({
      profile,
      loading,
      signIn,
      signUp,
      signOut,
      adoptSession,
      updateProfile: setProfile,
    }),
    [profile, loading, signIn, signUp, signOut, adoptSession],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession phải nằm trong <SessionProvider>");
  }
  return value;
}

/** Doi loi bat ky thanh thong bao tieng Viet doc duoc. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Đã xảy ra lỗi không xác định.";
}
