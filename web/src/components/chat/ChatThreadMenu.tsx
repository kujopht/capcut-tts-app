"use client";

/**
 * Menu "⋯" o dau cuoc tro chuyen (cua so dock + /messages):
 *
 *   Xem hồ sơ — trang ca nhan Fanfic cua nguoi kia.
 *   Mở trong trang Tin nhắn — CHI o cua so dock (`coTrangTin`).
 *   Tat / Bat thong bao — RIENG hoi thoai nay (`chat_members.muted`): tin van den, chi khong tinh vao
 *     tong tren nut Tin nhan. Lam ngay, bam lai la dao nguoc.
 *   Chan / Bo chan — MUC TAI KHOAN (`user_blocks` cua Social, #229 — CUNG thao tac voi nut Chan o trang ca
 *     nhan): hai ben khong gui tin moi cho nhau duoc nua; lich su cu van con, khong ai bi bao "ban da bi
 *     chan". Chan la thao tac manh -> ConfirmDialog (danger). Bo chan thi lam ngay.
 *   Báo cáo — `ReportDialog` cua Social (nguoi dung), CHI khi may chu bat `user_reports`.
 *
 * Hop thoai render qua PORTAL vao `body`: cua so chat co `backdrop-filter` nen moi `position: fixed`
 * ben trong bi giam trong khung (va bi `overflow: hidden` cat).
 *
 * Noi goi dat `key={peerId}`: doi nguoi = mount moi — menu/hop thoai/loi cua cuoc truoc khong mang sang.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ReportDialog } from "@/components/ReportDialog";
import { ConfirmDialog } from "@/components/ui";
import { useChat } from "./ChatProvider";

export function ChatThreadMenu({ peerId, peerName, coTrangTin = false }: {
  peerId: string;
  peerName: string;
  /** Cua so dock: them "Mở trong trang Tin nhắn". */
  coTrangTin?: boolean;
}) {
  const { canMute, canBlock, canReport, inboxLoaded, blocksLoaded, isMuted, blocked, setMuted, setBlocked,
    identityOf } = useChat();
  const router = useRouter();
  const it = identityOf(peerId);
  const hoSo = it?.found && it.username ? `/u/${it.username}` : null;
  const [baoCao, setBaoCao] = useState(false);
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
    return () => document.removeEventListener("pointerdown", ngoai);
  }, [mo]);

  // Tieu diem vao muc DAU TIEN bat duoc — ca khi muc vua het "Đang tải…" (tai hop thu/danh sach chan xong
  // SAU luc mo menu). Khong giat tieu diem neu nguoi dung da o trong menu.
  useEffect(() => {
    if (!mo) return;
    const khung = requestAnimationFrame(() => {
      const bang = hop.current?.querySelector('[role="menu"]');
      if (bang?.contains(document.activeElement)) return;
      bang?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus();
    });
    return () => cancelAnimationFrame(khung);
  }, [mo, inboxLoaded, blocksLoaded]);

  const coBaoCaoNguoi = canReport && Boolean(it?.found && it.user_id);
  if (!canMute && !canBlock && !hoSo && !coTrangTin && !coBaoCaoNguoi) return null;

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
        const muc = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')];
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
          {hoSo ? (
            <Link href={hoSo} role="menuitem" className="chat-menu-muc" prefetch={false} onClick={() => setMo(false)}>
              <span aria-hidden="true">👤</span>
              Xem hồ sơ
            </Link>
          ) : null}
          {coTrangTin ? (
            <button type="button" role="menuitem" className="chat-menu-muc"
              onClick={() => {
                setMo(false);
                router.push(`/messages?c=${encodeURIComponent(peerId)}`);
              }}>
              <span aria-hidden="true">⤢</span>
              Mở trong trang Tin nhắn
            </button>
          ) : null}
          {/* Chua tai hop thu / danh sach chan: CHUA BIET trang thai that -> khoa muc, khong doan. */}
          {canMute ? (
            <button type="button" role="menuitem" className="chat-menu-muc" disabled={!inboxLoaded}
              onClick={() => void doiTatTieng()}>
              <span aria-hidden="true">{tatTieng ? "🔔" : "🔕"}</span>
              {!inboxLoaded ? "Đang tải…" : tatTieng ? "Bật thông báo" : "Tắt thông báo"}
            </button>
          ) : null}
          {canBlock ? (
            !blocksLoaded ? (
              <button type="button" role="menuitem" className="chat-menu-muc" disabled>
                <span aria-hidden="true">⛔</span>
                Đang tải…
              </button>
            ) : daChan ? (
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
          {coBaoCaoNguoi ? (
            <button type="button" role="menuitem" className="chat-menu-muc"
              onClick={() => {
                setMo(false);
                setBaoCao(true);
              }}>
              <span aria-hidden="true">🚩</span>
              Báo cáo
            </button>
          ) : null}
        </div>
      ) : null}
      {baoCao && it?.user_id ? (
        <ReportDialog targetKind="user" targetId={it.user_id} targetName={peerName} onClose={() => setBaoCao(false)} />
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
                  <p>Chặn áp dụng cho cả tài khoản — là CÙNG một lần chặn với nút Chặn ở trang cá nhân. Bạn có thể bỏ
                    chặn bất cứ lúc nào.</p>
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
