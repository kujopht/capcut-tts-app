"use client";

/** Toast dung chung. Thong bao ngan sau moi thao tac, tu tat sau vai giay. */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

type ToastKind = "ok" | "error" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastValue {
  push: (kind: ToastKind, message: string) => void;
  ok: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastValue | null>(null);
const ICON: Record<ToastKind, string> = { ok: "✅", error: "⛔", info: "ℹ️" };
const LIFETIME_MS = 4500;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      seq.current += 1;
      const id = seq.current;
      setItems((current) => [...current.slice(-3), { id, kind, message }]);
      window.setTimeout(() => dismiss(id), LIFETIME_MS);
    },
    [dismiss],
  );

  const value = useMemo<ToastValue>(
    () => ({
      push,
      ok: (message: string) => push("ok", message),
      error: (message: string) => push("error", message),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* aria-live de doc man hinh doc duoc thong bao ma khong cuop focus */}
      <div className="toast-wrap" aria-live="polite" aria-atomic="false">
        {items.map((item) => (
          <output key={item.id} className={`toast toast-${item.kind}`}>
            <span className="toast-icon" aria-hidden="true">
              {ICON[item.kind]}
            </span>
            <span style={{ flex: 1 }}>{item.message}</span>
            <button
              type="button"
              className="toast-close"
              onClick={() => dismiss(item.id)}
              aria-label="Đóng thông báo"
            >
              ✕
            </button>
          </output>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast phải nằm trong <ToastProvider>");
  return value;
}
