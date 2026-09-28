"use client";

/**
 * Menu "⋯" o dau cuoc tro chuyen (drawer + /messages):
 *
 *   Tat / Bat thong bao — RIENG hoi thoai nay (`chat_members.muted`): tin van den, chi khong tinh vao
 *     tong tren nut Tin nhan. Lam ngay, bam lai la dao nguoc.
 *   Chan / Bo chan — MUC TAI KHOAN (hang `user_blocks`, cung dinh dang voi chan o trang ca nhan): hai
 *     ben khong gui tin moi cho nhau duoc nua; lich su cu van con, khong ai bi bao "ban da bi chan".
 *     Chan la thao tac manh -> ConfirmDialog (danger). Bo chan thi lam ngay.
 *
 * Hop thoai render qua PORTAL vao `body`: `.chat-drawer` co `backdrop-filter` nen moi `position: fixed`
 * ben trong bi giam trong khung (va bi `overflow: hidden` cat).
 *
 * Noi goi dat `key={peerId}`: doi nguoi = mount moi — menu/hop thoai/loi cua cuoc truoc khong mang sang.
 */
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ConfirmDialog } from "@/components/ui";
import { useChat } from "./ChatProvider";

export function ChatThreadMenu({ peerId, peerName }: { peerId: string; peerName: string }) {
  const { canMute, canBlock, isMuted, blocked, setMuted, setBlocked } = useChat();
  const [mo, setMo] = useState(false);
  const [hoiChan, setHoiChan] = useState(false);
  const [dangLam, setDangLam] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const hop = useRef<HTMLDivElement | null>(null);
  const nut = useRef<HTMLButtonElement | null>(null);
  const menuId = useId();
  const tatTieng = isMuted(peerId);
  const daChan = !!blocked[peerId];

  useEffect(() => {
    if (!mo) return;
    const ngoai = (e: PointerEvent) => {
      if (!hop.current?.contains(e.target as Node)) setMo(false);
    };
    document.addEventListener("pointerdown", ngoai);
    const khung = requestAnimationFrame(() => hop.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus());
    return () => {
      cancelAnimationFrame(khung);
      document.removeEventListener("pointerdown", ngoai);
    };
  }, [mo]);

  if (!canMute && !canBlock) return null;

  const dongMenu = () => {
    setMo(false);
    nut.current?.focus();
  };

  const doiTatTieng = async () => {
    dongMenu();
    setLoi(null);
    setDangLam(true);
    try {
      await setMuted(peerId, !tatTieng);
    } catch {
      setLoi(tatTieng ? "Chưa bật lại thông báo được. Thử lại sau." : "Chưa tắt thông báo được. Thử lại sau.");
    } finally {
      setDangLam(false);
    }
  };

  const boChan = async () => {
    dongMenu();
    setLoi(null);
    setDangLam(true);
    try {
      await setBlocked(peerId, false);
    } catch {
      setLoi("Chưa bỏ chặn được. Thử lại sau.");
    } finally {
      setDangLam(false);
    }
  };

  const chanThat = async () => {
    setLoi(null);
    setDangLam(true);
    try {
      await setBlocked(peerId, true);
      setHoiChan(false);
      nut.current?.focus();
    } catch {
      setLoi("Chưa chặn được. Thử lại sau.");
    } finally {
      setDangLam(false);
    }
  };

  return (
    <div
      ref={hop}
      className="chat-menu"
      onKeyDown={(e) => {
        if (!mo) return;
        if (e.key === "Escape") {
          // Chi dong MENU — khong de Escape noi len drawer va dong ca cuoc tro chuyen.
          e.stopPropagation();
          dongMenu();
          return;
        }
        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
        const muc = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')];
        const i = muc.indexOf(document.activeElement as HTMLButtonElement);
        e.preventDefault();
        muc[(i + (e.key === "ArrowDown" ? 1 : muc.length - 1) + muc.length) % muc.length]?.focus();
      }}
    >
      <button
        ref={nut}
        type="button"
        className="chat-nut"
        aria-label={`Tuỳ chọn cuộc trò chuyện với ${peerName}`}
        title="Tuỳ chọn"
        aria-haspopup="menu"
        aria-expanded={mo}
        aria-controls={mo ? menuId : undefined}
        disabled={dangLam}
        onClick={() => setMo((v) => !v)}
      >
        <span aria-hidden="true">⋯</span>
      </button>
      {mo ? (
        <div id={menuId} className="chat-menu-bang" role="menu" aria-label="Tuỳ chọn cuộc trò chuyện">
          {canMute ? (
            <button type="button" role="menuitem" className="chat-menu-muc" onClick={() => void doiTatTieng()}>
              <span aria-hidden="true">{tatTieng ? "🔔" : "🔕"}</span>
              {tatTieng ? "Bật thông báo" : "Tắt thông báo"}
            </button>
          ) : null}
          {canBlock ? (
            daChan ? (
              <button type="button" role="menuitem" className="chat-menu-muc" onClick={() => void boChan()}>
                <span aria-hidden="true">↺</span>
                Bỏ chặn
              </button>
            ) : (
              <button
                type="button"
                role="menuitem"
                className="chat-menu-muc chat-menu-muc-nguy"
                onClick={() => {
                  setMo(false);
                  setLoi(null);
                  setHoiChan(true);
                }}
              >
                <span aria-hidden="true">⛔</span>
                Chặn người này
              </button>
            )
          ) : null}
        </div>
      ) : null}
      {loi && !hoiChan ? <span className="chat-menu-loi" role="alert">{loi}</span> : null}
      {hoiChan && typeof document !== "undefined"
        ? createPortal(
            <ConfirmDialog
              open
              danger
              busy={dangLam}
              title={`Chặn ${peerName}?`}
              confirmLabel="Chặn"
              cancelLabel="Huỷ"
              body={
                <>
                  <p>
                    Hai bạn sẽ không gửi được tin nhắn mới cho nhau. Tin nhắn cũ vẫn còn trong lịch sử. {peerName} không
                    nhận được thông báo nào về việc này.
                  </p>
                  <p>Chặn áp dụng cho cả tài khoản — giống chặn ở trang cá nhân. Bạn có thể bỏ chặn bất cứ lúc nào.</p>
                  {loi ? <p className="chat-menu-loi-hop" role="alert">{loi}</p> : null}
                </>
              }
              onConfirm={() => void chanThat()}
              onCancel={() => {
                if (dangLam) return;
                setHoiChan(false);
                setLoi(null);
                // Muc menu da mo hop thoai khong con nua — tra tieu diem ve nut "⋯".
                requestAnimationFrame(() => nut.current?.focus());
              }}
            />,
            document.body,
          )
        : null}
    </div>
  );
}
