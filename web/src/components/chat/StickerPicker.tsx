"use client";

/**
 * Bo chon NHAN DAN — tab: Gần đây, Yêu thích, roi tung goi (goi KHOA hien dieu kien mo khoa, nhan dan mo
 * mo, khong gui duoc — may chu cung tu choi 403). Catalog tai LUOI lan dau mo (`loadStickers`), trang thai
 * khoa do MAY CHU quyet theo nguoi xem. Gan day / Yeu thich: `localStorage` theo nguoi (lib/chat/stickerPrefs).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { StickerPackDto } from "@/lib/api";
import type { StickerRef } from "@/lib/chat/types";
import { PREFS_RONG, docPrefs, doiYeuThich, khoaPrefs, themGanDay, type StickerPrefs } from "@/lib/chat/stickerPrefs";
import { useChat } from "./ChatProvider";

function docLuu(me: string | null): StickerPrefs {
  if (!me || typeof window === "undefined") return PREFS_RONG;
  try {
    return docPrefs(window.localStorage.getItem(khoaPrefs(me)));
  } catch {
    return PREFS_RONG;
  }
}

type TabId = "recent" | "fav" | string;

export function StickerPicker({ onPick, onClose }: { onPick: (s: StickerRef) => void; onClose: () => void }) {
  const { stickerPacks, loadStickers, me } = useChat();
  const [prefs, setPrefs] = useState<StickerPrefs>(() => docLuu(me));
  const [tab, setTab] = useState<TabId | null>(null);
  const hop = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    loadStickers();
  }, [loadStickers]);

  useEffect(() => {
    if (!me) return;
    try {
      window.localStorage.setItem(khoaPrefs(me), JSON.stringify(prefs));
    } catch {
      /* localStorage bi chan — chi mat Gan day/Yeu thich */
    }
  }, [me, prefs]);

  useEffect(() => {
    const ngoai = (e: PointerEvent) => {
      const el = e.target as Element | null;
      if (!hop.current?.contains(el) && !el?.closest?.(".chat-nut-nhan-dan")) onClose();
    };
    document.addEventListener("pointerdown", ngoai);
    return () => document.removeEventListener("pointerdown", ngoai);
  }, [onClose]);

  const theoId = useMemo(() => {
    const m = new Map<string, { s: StickerRef; pack: StickerPackDto }>();
    for (const p of stickerPacks ?? []) for (const s of p.stickers) m.set(s.id, { s, pack: p });
    return m;
  }, [stickerPacks]);

  const dangTab: TabId = tab ?? (prefs.recent.some((id) => theoId.has(id)) ? "recent" : stickerPacks?.[0]?.id ?? "recent");
  const goi = stickerPacks?.find((p) => p.id === dangTab) ?? null;
  const ds: { s: StickerRef; locked: boolean }[] = dangTab === "recent" || dangTab === "fav"
    ? (dangTab === "recent" ? prefs.recent : prefs.favorites)
      .map((id) => theoId.get(id))
      .filter((x): x is { s: StickerRef; pack: StickerPackDto } => !!x)
      .map((x) => ({ s: x.s, locked: x.pack.locked }))
    : (goi?.stickers ?? []).map((s) => ({ s, locked: !!goi?.locked }));

  const chon = (s: StickerRef) => {
    setPrefs((p) => themGanDay(p, s.id));
    onPick(s);
  };

  return (
    <div ref={hop} className="chat-nd" role="dialog" aria-label="Nhãn dán"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}>
      <div className="chat-nd-tab" role="tablist" aria-label="Nhóm nhãn dán">
        <button type="button" role="tab" aria-selected={dangTab === "recent"} className="chat-nd-tab-nut"
          onClick={() => setTab("recent")} title="Gần đây"><span aria-hidden="true">🕘</span><span className="sr-only">Gần đây</span></button>
        <button type="button" role="tab" aria-selected={dangTab === "fav"} className="chat-nd-tab-nut"
          onClick={() => setTab("fav")} title="Yêu thích"><span aria-hidden="true">★</span><span className="sr-only">Yêu thích</span></button>
        {(stickerPacks ?? []).map((p) => (
          <button key={p.id} type="button" role="tab" aria-selected={dangTab === p.id} className="chat-nd-tab-nut chat-nd-tab-goi"
            onClick={() => setTab(p.id)} title={p.locked ? `${p.name} — ${p.unlock.label}` : p.name}>
            {p.locked ? <span aria-hidden="true">🔒</span> : null}
            <span className="truncate">{p.name}</span>
          </button>
        ))}
      </div>
      <div className="chat-nd-than" role="tabpanel">
        {stickerPacks === null ? <p className="hint chat-nd-trong">Đang tải nhãn dán…</p> : null}
        {stickerPacks !== null && !stickerPacks.length ? <p className="hint chat-nd-trong">Chưa tải được nhãn dán.</p> : null}
        {goi?.locked ? <p className="chat-nd-khoa" role="note">🔒 {goi.unlock.label || "Gói này chưa mở khoá."}</p> : null}
        {stickerPacks?.length && !ds.length ? (
          <p className="hint chat-nd-trong">
            {dangTab === "fav" ? "Chưa có nhãn dán yêu thích — bấm ☆ trên một nhãn dán." : "Chưa dùng nhãn dán nào."}
          </p>
        ) : null}
        <ul className="chat-nd-luoi">
          {ds.map(({ s, locked }) => {
            const thich = prefs.favorites.includes(s.id);
            return (
              <li key={s.id} className="chat-nd-o">
                <button type="button" className="chat-nd-nut" disabled={locked} aria-disabled={locked}
                  aria-label={locked ? `${s.alt} — chưa mở khoá` : `Gửi nhãn dán ${s.alt}`} title={s.alt}
                  onClick={() => chon(s)}>
                  {/* eslint-disable-next-line @next/next/no-img-element -- anh tinh nho, KHONG qua toi uu anh */}
                  <img src={s.url} alt="" width={64} height={64} loading="lazy" draggable={false} />
                </button>
                {!locked ? (
                  <button type="button" className="chat-nd-thich" aria-pressed={thich}
                    aria-label={thich ? `Bỏ yêu thích ${s.alt}` : `Yêu thích ${s.alt}`}
                    onClick={() => setPrefs((p) => doiYeuThich(p, s.id))}>
                    <span aria-hidden="true">{thich ? "★" : "☆"}</span>
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
