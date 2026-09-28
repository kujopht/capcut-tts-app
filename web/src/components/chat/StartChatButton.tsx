"use client";

/**
 * "Nhắn tin" o trang ca nhan. Chi hien khi DA DANG NHAP (khach khong co hop
 * thu) va khong phai ho so cua chinh minh (trang goi da loc `is_self`).
 * Bam = nguoi dung chu dong mo chat -> `nhanTinVoi` goi `moChat("profile-dm")`.
 */
import { useState } from "react";
import { useSession } from "@/lib/session";
import { useChat } from "./ChatProvider";

export function StartChatButton({ username, displayName }: { username: string; displayName: string }) {
  const { profile } = useSession();
  const { nhanTinVoi } = useChat();
  const [dang, setDang] = useState(false);
  if (!profile) return null;
  return (
    <button
      type="button"
      className="btn btn-outline btn-sm"
      disabled={dang}
      aria-label={`Nhắn tin cho ${displayName}`}
      onClick={async () => {
        setDang(true);
        try {
          await nhanTinVoi(username);
        } finally {
          setDang(false);
        }
      }}
    >
      {dang ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">💬</span>} Nhắn tin
    </button>
  );
}
