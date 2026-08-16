"use client";

/**
 * Hop thoai ket noi provider AI CA NHAN (V5.1 BYOK, Part A/C — tong quat
 * hoa cho NHIEU provider o V6 cerebras-groq-translation: Groq VA Cerebras
 * dung CHUNG mot hop thoai, chi khac props hien thi/URL).
 *
 * Luong: dan key -> "Kiểm tra kết nối" (goi THANG `translate.connectProvider`
 * — kiem tra VA luu trong CUNG mot request o backend, khong co buoc "xac
 * thuc roi luu rieng"; that bai thi KHONG luu gi) -> thanh cong hien trang
 * thai xac nhan + nut "Lưu kết nối" chi de DONG hop thoai (da luu roi).
 *
 * KHONG BAO GIO hien lai key day du sau khi da gui — chi 4 ky tu cuoi
 * (`last4` tu may chu, khong tu cat chuoi o frontend).
 */

import { useEffect, useRef, useState } from "react";
import { translate, type ProviderConnection } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { Alert } from "@/components/ui";

function nhanLoiKetNoi(tenProvider: string): Record<string, string> {
  return {
    INVALID_KEY: "API key không hợp lệ. Kiểm tra lại bạn đã sao chép đúng key chưa.",
    RATE_LIMITED: `${tenProvider} đang giới hạn tốc độ — thử lại sau ít phút.`,
    PROVIDER_UNAVAILABLE: `Không kết nối được ${tenProvider} lúc này. Thử lại sau.`,
    MODEL_UNAVAILABLE: "Model mặc định không khả dụng với API key này.",
  };
}

export default function ProviderConnectDialog({
  open,
  onClose,
  onConnected,
  providerId = "groq",
  providerLabel = "Groq",
  consoleUrl,
  keyPlaceholder = "................................",
}: {
  open: boolean;
  onClose: () => void;
  onConnected: (connection: ProviderConnection) => void;
  /** ID provider goi API — "groq" | "cerebras". */
  providerId?: string;
  /** Ten hien thi trong tieu de hop thoai va thong bao loi. */
  providerLabel?: string;
  /** Trang tao API key CUA CHINH provider do. */
  consoleUrl: string;
  /** Vi du dinh dang key, hien trong o nhap (khong phai gia tri that). */
  keyPlaceholder?: string;
}) {
  const [apiKey, setApiKey] = useState("");
  const [dangKiemTra, setDangKiemTra] = useState(false);
  const [loi, setLoi] = useState("");
  const [ketQua, setKetQua] = useState<ProviderConnection | null>(null);
  const hop = useRef<HTMLDivElement | null>(null);
  /** Phan tu giu tieu diem TRUOC khi mo — tra ve dung no khi dong. */
  const truoc = useRef<HTMLElement | null>(null);

  const dong = () => {
    setApiKey("");
    setLoi("");
    setKetQua(null);
    onClose();
  };

  /* Giu ham DONG moi nhat trong mot ref, KHONG dua vao mang phu thuoc cua
     effect ben duoi — cung ly do voi `ConfirmDialog` (`components/ui.tsx`):
     go phim vao o nhap API key lam component render lai, tao mot `dong` MOI
     moi lan; neu no nam trong deps thi effect don-roi-chay-lai sau MOI PHIM
     GO va giat tieu diem ra khoi o nhap. */
  const dongRef = useRef(dong);
  useEffect(() => {
    dongRef.current = dong;
  });

  /* Tieu diem vao hop thoai khi mo, Escape dong, tra tieu diem ve nut da mo
     khi dong — cung quy tac voi moi hop thoai khac cua app (xem
     `ReportDialog`, `ImageLightbox`). */
  useEffect(() => {
    if (!open) return;
    truoc.current = document.activeElement as HTMLElement | null;
    hop.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        dongRef.current();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      truoc.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  const kiemTraVaKetNoi = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) return;
    setDangKiemTra(true);
    setLoi("");
    try {
      const { connection } = await translate.connectProvider(providerId, apiKey.trim());
      setKetQua(connection);
      onConnected(connection);
    } catch (cause) {
      const ma = cause instanceof ApiError ? cause.code : undefined;
      setLoi((ma && nhanLoiKetNoi(providerLabel)[ma]) || errorMessage(cause));
    } finally {
      setDangKiemTra(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={(e) => {
      if (e.target === e.currentTarget) dong();
    }}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="byok-title"
        tabIndex={-1}
        ref={hop}
      >
        <h2 id="byok-title">{providerLabel} cá nhân</h2>
        <div className="stack-2 modal-body">
          {ketQua ? (
            <div className="stack-2">
              <Alert kind="ok">Kết nối thành công</Alert>
              <p>
                {providerLabel}
                <br />
                Key: ••••••••{ketQua.last4}
              </p>
            </div>
          ) : (
            <form className="stack-2" onSubmit={kiemTraVaKetNoi}>
              <div className="stack-2">
                <p><strong>1. Tạo API key {providerLabel}</strong></p>
                <a
                  className="btn btn-outline btn-sm"
                  href={consoleUrl}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                >
                  Mở trang tạo API key ↗
                </a>
                <p className="hint">
                  Đăng nhập {providerLabel}, tạo API key mới, sau đó sao chép
                  key và dán vào đây.
                </p>
              </div>
              <div className="field">
                <label className="label" htmlFor="byok-key">2. API key</label>
                <input
                  id="byok-key"
                  className="input"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={keyPlaceholder}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={dangKiemTra}
                />
              </div>
              {loi ? <Alert kind="error">{loi}</Alert> : null}
              <button type="submit" className="btn btn-primary" disabled={dangKiemTra || !apiKey.trim()}>
                {dangKiemTra ? <span className="spinner" aria-hidden="true" /> : null}
                Kiểm tra kết nối
              </button>
            </form>
          )}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={dong}>
            {ketQua ? "Đóng" : "Huỷ"}
          </button>
          {ketQua ? (
            <button type="button" className="btn btn-primary" onClick={dong}>
              Lưu kết nối
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
