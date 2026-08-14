"use client";

/**
 * Hop thoai ket noi provider AI CA NHAN (V5.1 BYOK, Part A/C).
 *
 * Luong: dan key -> "Kiểm tra kết nối" (goi THANG `translate.connectProvider`
 * — kiem tra VA luu trong CUNG mot request o backend, khong co buoc "xac
 * thuc roi luu rieng"; that bai thi KHONG luu gi) -> thanh cong hien trang
 * thai xac nhan + nut "Lưu kết nối" chi de DONG hop thoai (da luu roi).
 *
 * KHONG BAO GIO hien lai key day du sau khi da gui — chi 4 ky tu cuoi
 * (`last4` tu may chu, khong tu cat chuoi o frontend).
 */

import { useState } from "react";
import { translate, GROQ_CONSOLE_KEYS_URL, type ProviderConnection } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { Alert } from "@/components/ui";

const NHAN_LOI_KET_NOI: Record<string, string> = {
  INVALID_KEY: "API key không hợp lệ. Kiểm tra lại bạn đã sao chép đúng key chưa.",
  RATE_LIMITED: "Groq đang giới hạn tốc độ — thử lại sau ít phút.",
  PROVIDER_UNAVAILABLE: "Không kết nối được Groq lúc này. Thử lại sau.",
  MODEL_UNAVAILABLE: "Model mặc định không khả dụng với API key này.",
};

export default function ProviderConnectDialog({
  open,
  onClose,
  onConnected,
}: {
  open: boolean;
  onClose: () => void;
  onConnected: (connection: ProviderConnection) => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [dangKiemTra, setDangKiemTra] = useState(false);
  const [loi, setLoi] = useState("");
  const [ketQua, setKetQua] = useState<ProviderConnection | null>(null);

  if (!open) return null;

  const dong = () => {
    setApiKey("");
    setLoi("");
    setKetQua(null);
    onClose();
  };

  const kiemTraVaKetNoi = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) return;
    setDangKiemTra(true);
    setLoi("");
    try {
      const { connection } = await translate.connectProvider("groq", apiKey.trim());
      setKetQua(connection);
      onConnected(connection);
    } catch (cause) {
      const ma = cause instanceof ApiError ? cause.code : undefined;
      setLoi((ma && NHAN_LOI_KET_NOI[ma]) || errorMessage(cause));
    } finally {
      setDangKiemTra(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={(e) => {
      if (e.target === e.currentTarget) dong();
    }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="byok-title">
        <h2 id="byok-title">Groq cá nhân</h2>
        <div className="stack-2 modal-body">
          {ketQua ? (
            <div className="stack-2">
              <Alert kind="ok">Kết nối thành công</Alert>
              <p>
                Groq · Qwen
                <br />
                Key: ••••••••{ketQua.last4}
              </p>
            </div>
          ) : (
            <form className="stack-2" onSubmit={kiemTraVaKetNoi}>
              <div className="stack-2">
                <p><strong>1. Tạo API key Groq</strong></p>
                <a
                  className="btn btn-outline btn-sm"
                  href={GROQ_CONSOLE_KEYS_URL}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                >
                  Mở trang tạo API key ↗
                </a>
                <p className="hint">
                  Đăng nhập Groq, nhấn Create API Key, sau đó sao chép key và
                  dán vào đây.
                </p>
              </div>
              <div className="field">
                <label className="label" htmlFor="byok-key">2. API key</label>
                <input
                  id="byok-key"
                  className="input"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="gsk_................................"
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
