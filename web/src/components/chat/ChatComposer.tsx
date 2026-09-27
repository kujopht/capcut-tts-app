"use client";

/**
 * O soan tin.
 *
 * Enter = gui, Shift+Enter = xuong dong — NHUNG KHONG khi bo go dang "soan"
 * (`isComposing` / keyCode 229). Bo go tieng Viet (Telex/VNI, go dau tren
 * Windows/macOS/Android) giu chu trong trang thai soan; Enter luc do la de
 * CHOT chu, khong phai de gui — gui luc do se gui nua chu va nuot dau.
 *
 * Mat mang: van cho go (nhap duoc giu o `ChatProvider`), chi khoa nut gui.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useChat } from "./ChatProvider";

const TOI_DA = 2000;
const EMOJI = ["😀", "😂", "🥰", "😍", "😅", "😭", "😢", "🤔", "👍", "🙏", "👏", "❤️", "🔥", "🎉", "✨", "👀"];

export function ChatComposer({ peerId, peerName, autoFocus = false }: { peerId: string; peerName?: string; autoFocus?: boolean }) {
  const { drafts, setDraft, send, status } = useChat();
  const gt = drafts[peerId] ?? "";
  const o = useRef<HTMLTextAreaElement | null>(null);
  const [moEmoji, setMoEmoji] = useState(false);
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
    send(peerId, gt);
    setMoEmoji(false);
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
    <form className="chat-soan" onSubmit={(e) => { e.preventDefault(); gui(); }}>
      <div className="chat-soan-emoji">
        <button
          type="button"
          className="chat-nut"
          aria-label="Chèn biểu tượng cảm xúc"
          aria-expanded={moEmoji}
          onClick={() => setMoEmoji((v) => !v)}
        >
          <span aria-hidden="true">😊</span>
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
          if (e.key === "Escape" && moEmoji) {
            e.stopPropagation();
            setMoEmoji(false);
            return;
          }
          if (e.key !== "Enter" || e.shiftKey) return;
          if (e.nativeEvent.isComposing || e.keyCode === 229) return; // bo go dang soan chu
          e.preventDefault();
          gui();
        }}
      />
      <button type="submit" className="chat-nut chat-nut-gui" disabled={!guiDuoc || rong}
        aria-label={guiDuoc ? "Gửi tin nhắn" : "Chưa gửi được — đang chờ kết nối"}>
        <span aria-hidden="true">➤</span>
      </button>
      {gt.length > TOI_DA - 200 ? <span className="hint chat-soan-dem" aria-live="polite">{gt.length}/{TOI_DA}</span> : null}
    </form>
  );
}
