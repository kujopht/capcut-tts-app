"use client";

/**
 * Vo cua thanh dieu huong. Chi lam MOT viec: biet trang da duoc cuon chua.
 *
 * VI SAO CAN BIET: header trong suot co lop mo phia sau. Khi trang con o dinh
 * thi khong co gi troi qua duoi no, va mot vien dam o do chi to them mot vach
 * thua. Khi da cuon thi chu chay qua ngay duoi header va doc xuyen qua lop mo
 * — luc do moi can nen dac hon.
 *
 * Danh dau bang `data-scrolled` chu khong doi `className`: mau va do dam nam
 * o CSS, va cho nay khong nen biet chung trong nhu the nao.
 *
 * `children` van duoc dat o `layout.tsx` — thuong hieu, dieu huong, tim kiem,
 * tai khoan deu o nguyen cho cu. Tep nay khong quyet dinh thu tu cua chung.
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import { DockSoundwaveFrame } from "@/components/DockSoundwaveFrame";
import { musicStore } from "@/lib/musicStore";

/** Cuon qua bay nhieu pixel thi coi la "da roi dinh trang". */
const NGUONG = 8;

export function SiteHeader({ children }: { children: React.ReactNode }) {
  const [daCuon, setDaCuon] = useState(false);
  const { isPlaying, currentTrack } = useSyncExternalStore(
    musicStore.subscribe,
    musicStore.getSnapshot,
    () => musicStore.getSnapshot(),
  );

  useEffect(() => {
    // `passive`: cho trinh duyet biet ham nay khong goi `preventDefault`, nen
    // no khong phai cho ta chay xong moi cuon tiep.
    const doc = () => setDaCuon(window.scrollY > NGUONG);
    doc();
    window.addEventListener("scroll", doc, { passive: true });
    if (typeof window !== "undefined") {
      (window as unknown as { __musicStore: unknown }).__musicStore = musicStore;
    }
    return () => window.removeEventListener("scroll", doc);
  }, []);

  const headerStyle = isPlaying
    ? ({ "--music-wave-color": currentTrack?.color || "rgba(56, 189, 248, 1)" } as React.CSSProperties)
    : undefined;

  return (
    <header
      className="site-header"
      data-scrolled={daCuon ? "true" : undefined}
      data-music-playing={isPlaying ? "true" : undefined}
      style={headerStyle}
    >
      <DockSoundwaveFrame />
      {children}
    </header>
  );
}
