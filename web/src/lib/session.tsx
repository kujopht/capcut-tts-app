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
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  // Khoi phuc phien khi tai lai trang
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((r) => {
        if (!cancelled) setProfile(r.profile);
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

  const signOut = useCallback(() => {
    setToken(null);
    setProfile(null);
  }, []);

  const value = useMemo<SessionValue>(
    () => ({ profile, loading, signIn, signUp, signOut }),
    [profile, loading, signIn, signUp, signOut],
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
