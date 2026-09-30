"use client";

/**
 * Nut Tin nhan tren thanh dieu huong — dung CANH chuong thong bao, cung kich
 * thuoc/cham so (`.bell`/`.bell-dot`) de hai nut doc nhu mot bo.
 *
 * Ve nut KHONG mo chat. Chi BAM moi goi `moChat("inbox")` — ai khong bam thi
 * khong co phien, khong tai SDK, khong tinh MAU. Cham so chua doc chi co sau
 * khi da mo mot lan (truoc do khong co gi de dem ma khong dang nhap Tencent).
 *
 * Desktop: mo bang Tin nhan. Di dong: sang /messages (bang nho khong co cho).
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { CHAT_V1_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";
import { MAN_HINH_CHAT_NHO, useChat } from "./ChatProvider";
import { InboxPopover } from "./InboxPopover";
import { FanficIcon } from "@/components/icons/FanficIcon";

export function ChatLauncher() {
  const { profile } = useSession();
  const { unreadTotal, moChat, available } = useChat();
  const router = useRouter();
  const [mo, setMo] = useState(false);
  const hop = useRef<HTMLDivElement | null>(null);
  const nut = useRef<HTMLButtonElement | null>(null);
  const dong = useCallback(() => setMo(false), []);

  useEffect(() => {
    if (!mo) return;
    const onDown = (e: MouseEvent) => {
      if (!hop.current?.contains(e.target as Node)) dong();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      dong();
      nut.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [mo, dong]);

  if (!CHAT_V1_ENABLED) return null;
  if (!profile) return null;
  // May chu chua mo chat cho tai khoan nay (canary) / dang hoi: khong ve nut.
  if (available !== true) return null;

  const bam = () => {
    if (window.matchMedia(MAN_HINH_CHAT_NHO).matches) {
      router.push("/messages");
      return;
    }
    setMo((v) => !v);
    void moChat("inbox");
  };

  return (
    <div className="menu" ref={hop}>
      <button
        ref={nut}
        type="button"
        className="bell chat-launcher"
        aria-haspopup="dialog"
        aria-expanded={mo}
        aria-label={unreadTotal > 0 ? `Tin nhắn, ${unreadTotal} chưa đọc` : "Tin nhắn"}
        onClick={bam}
      >
        <FanficIcon name="message" size={20} />
        {unreadTotal > 0 ? (
          <span className="bell-dot" aria-hidden="true">{unreadTotal > 9 ? "9+" : unreadTotal}</span>
        ) : null}
      </button>
      {mo ? <InboxPopover onClose={dong} /> : null}
    </div>
  );
}
