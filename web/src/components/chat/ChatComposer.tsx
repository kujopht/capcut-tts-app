"use client";

/**
 * O soan tin.
 *
 * Enter = gui, Shift+Enter = xuong dong — NHUNG KHONG khi bo go dang "soan"
 * (`isComposing` / keyCode 229). Bo go tieng Viet (Telex/VNI, go dau tren
 * Windows/macOS/Android) giu chu trong trang thai soan; Enter luc do la de
 * CHOT chu, khong phai de gui — gui luc do se gui nua chu va nuot dau.
 *
 * Bo go tieng Han/Nhat (IME) cung dung `isComposing` nhu vay.
 *
 * Mat mang: van cho go (nhap duoc giu o `ChatProvider`), chi khoa nut gui.
 *
 * Hai hang (hop voi cua so dock hep): o nhap o tren; hang cong cu 😊 · nhan dan · 📎 (dinh kem — CHUA co,
 * vo hieu hoa, khong gia vo) · gui o duoi.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { StickerRef } from "@/lib/chat/types";
import { useChat } from "./ChatProvider";
import { StickerPicker } from "./StickerPicker";
import { FanficIcon } from "@/components/icons/FanficIcon";

const TOI_DA = 2000;
const EMOJI = ["😀", "😂", "🥰", "😍", "😅", "😭", "😢", "🤔", "👍", "🙏", "👏", "❤️", "🔥", "🎉", "✨", "👀"];

/**
 * Minh da chan nguoi nay: KHONG co o soan (may chu cung tu choi 403 `chat_blocked`) — thay bang mot dong
 * noi ro va nut Bo chan. Chi hien khi MINH chan; bi nguoi kia chan thi giao dien khong biet (co y).
 */
function DaChan({ peerId, peerName }: { peerId: string; peerName?: string }) {
  const { setBlocked } = useChat();
  const [dang, setDang] = useState(false);
  const [loi, setLoi] = useState(false);
  return (
    <div className="chat-soan chat-da-chan" role="status">
      <span className="chat-da-chan-chu">
        Bạn đã chặn {peerName ?? "người này"}. Hai bạn không gửi được tin nhắn mới cho nhau.
        {loi ? <span className="chat-menu-loi-hop"> Chưa bỏ chặn được — thử lại.</span> : null}
      </span>
      <button
        type="button"
        className="btn btn-outline btn-sm"
        disabled={dang}
        onClick={() => {
          setDang(true);
          setLoi(false);
          setBlocked(peerId, false).catch(() => setLoi(true)).finally(() => setDang(false));
        }}
      >
        Bỏ chặn
      </button>
    </div>
  );
}

/** Giai doan thu (canary): nguoi KIA chua trong nhom duoc dung chat — may chu se tu choi (403), nen noi that. */
function ChuaMo({ peerName }: { peerName?: string }) {
  return (
    <div className="chat-soan chat-da-chan" role="status">
      <span className="chat-da-chan-chu">
        {peerName ?? "Người này"} chưa dùng được Tin nhắn trong giai đoạn thử — sẽ mở cho mọi người sớm.
      </span>
    </div>
  );
}

export function ChatComposer(props: { peerId: string; peerName?: string; autoFocus?: boolean }) {
  const { blocked, identityOf } = useChat();
  if (blocked[props.peerId]) return <DaChan peerId={props.peerId} peerName={props.peerName} />;
  const it = identityOf(props.peerId);
  if (it?.found && it.chat_enabled === false) return <ChuaMo peerName={props.peerName} />;
  return <OSoan {...props} />;
}

/** Hai lan gui CUNG noi dung trong khoang nay (Enter bam kep, bam nut + Enter) = mot lan. */
const CHONG_GUI_TRUNG_MS = 800;

function OSoan({ peerId, peerName, autoFocus = false }: { peerId: string; peerName?: string; autoFocus?: boolean }) {
  const { drafts, setDraft, send, sendSticker, canSticker, status } = useChat();
  const gt = drafts[peerId] ?? "";
  const o = useRef<HTMLTextAreaElement | null>(null);
  const [moEmoji, setMoEmoji] = useState(false);
  const [moNhanDan, setMoNhanDan] = useState(false);
  const lanGuiRef = useRef<{ text: string; luc: number } | null>(null);
  const guiDuoc = status === "ready";
  const rong = !gt.trim();

  useLayoutEffect(() => {
    const el = o.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
    // Chi hien thanh cuon khi THAT SU vuot 132px — mot dong ma co mui ten cuon trong nhu loi.
    el.style.overflowY = el.scrollHeight > 132 ? "auto" : "hidden";
  }, [gt]);

  useEffect(() => {
    if (autoFocus) o.current?.focus();
  }, [peerId, autoFocus]);

  const gui = () => {
    if (!guiDuoc || rong) return;
    // Chong gui trung: nhap chua kip xoa (cung mot khung hinh) ma Enter/nut gui lai lan nua.
    const bay = Date.now();
    const truoc = lanGuiRef.current;
    if (truoc && truoc.text === gt && bay - truoc.luc < CHONG_GUI_TRUNG_MS) return;
    lanGuiRef.current = { text: gt, luc: bay };
    send(peerId, gt);
    setMoEmoji(false);
    requestAnimationFrame(() => o.current?.focus());
  };

  const guiNhanDan = (s: StickerRef) => {
    if (!guiDuoc) return;
    sendSticker(peerId, s);
    setMoNhanDan(false);
    requestAnimationFrame(() => o.current?.focus());
  };

  const chen = (em: string) => {
    const el = o.current;
    const dau = el?.selectionStart ?? gt.length;
    const cuoi = el?.selectionEnd ?? gt.length;
    const moi = (gt.slice(0, dau) + em + gt.slice(cuoi)).slice(0, TOI_DA);
    setDraft(peerId, moi);
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus();
      const vt = Math.min(dau + em.length, moi.length);
      el.setSelectionRange(vt, vt);
    });
  };

  return (
    <form className="chat-soan chat-soan-2" onSubmit={(e) => { e.preventDefault(); gui(); }}>
      {moNhanDan ? <StickerPicker onPick={guiNhanDan} onClose={() => setMoNhanDan(false)} /> : null}
      <textarea
        ref={o}
        className="chat-soan-o"
        rows={1}
        value={gt}
        maxLength={TOI_DA}
        /* Ngan, co y: ten nguoi nhan da o dau khung (va trong aria-label). Mot
           placeholder dai bi xuong dong trong o mot dong va hien thanh cuon. */
        placeholder="Nhắn tin…"
        aria-label={peerName ? `Nhắn tin cho ${peerName}` : "Nhập tin nhắn"}
        onChange={(e) => setDraft(peerId, e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && (moEmoji || moNhanDan)) {
            e.stopPropagation();
            setMoEmoji(false);
            setMoNhanDan(false);
            return;
          }
          if (e.key !== "Enter" || e.shiftKey) return;
          if (e.nativeEvent.isComposing || e.keyCode === 229) return; // bo go dang soan chu
          e.preventDefault();
          gui();
        }}
      />
      <div className="chat-soan-cong-cu">
        <div className="chat-soan-emoji">
          <button type="button" className="chat-nut" aria-label="Chèn biểu tượng cảm xúc" aria-expanded={moEmoji}
            title="Biểu tượng cảm xúc" onClick={() => { setMoEmoji((v) => !v); setMoNhanDan(false); }}>
            <FanficIcon name="emoji" size={18} />
          </button>
          {moEmoji ? (
            <div className="chat-emoji-bang" role="group" aria-label="Biểu tượng cảm xúc">
              {EMOJI.map((em) => (
                <button key={em} type="button" className="chat-emoji" onClick={() => chen(em)} aria-label={`Chèn ${em}`}>
                  {em}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        {canSticker ? (
          <button type="button" className="chat-nut chat-nut-nhan-dan" aria-label="Chọn nhãn dán" aria-expanded={moNhanDan}
            title="Nhãn dán" disabled={!guiDuoc} onClick={() => { setMoNhanDan((v) => !v); setMoEmoji(false); }}>
            <FanficIcon name="sticker" size={18} />
          </button>
        ) : null}
        {/* Dinh kem CHUA co (can R2 + quet noi dung) — nut hien de biet la se co, KHONG gia vo hoat dong. */}
        <button type="button" className="chat-nut" disabled aria-disabled="true"
          aria-label="Đính kèm tệp — sắp có" title="Đính kèm — sắp có">
          <FanficIcon name="attach" size={18} />
        </button>
        <span className="chat-soan-gian" />
        {gt.length > TOI_DA - 200 ? <span className="hint chat-soan-dem" aria-live="polite">{gt.length}/{TOI_DA}</span> : null}
        <button type="submit" className="chat-nut chat-nut-gui" disabled={!guiDuoc || rong}
          aria-label={guiDuoc ? "Gửi tin nhắn" : "Chưa gửi được — đang chờ kết nối"}>
          <FanficIcon name="send" size={16} />
        </button>
      </div>
    </form>
  );
}
