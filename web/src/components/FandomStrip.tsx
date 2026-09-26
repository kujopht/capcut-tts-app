"use client";

/**
 * Dai chip "Khám phá theo vũ trụ" (trang chu) — lay tu DU LIEU THAT
 * (Product UX Sprint 2).
 *
 * Ban truoc dat cung nam chip; hai chip ("Fairy Tail", "Bóng rổ") dan toi
 * trang rong vi kho doc duoc KHONG co truyen nao cua hai vu tru do (do that
 * 2026-09-25). Nay chip = fandom CO truyen trong kho doc duoc, kem so truyen,
 * dan toi Thu vien da loc san. Anh chup kho dung chung voi Thu vien va o tim
 * (`lib/catalogSnapshot.ts`) nen khong ton them request.
 */

import Link from "next/link";
import { useAsyncData } from "@/lib/useAsyncData";
import { taiAnhChupKho } from "@/lib/catalogSnapshot";
import { chipFandom, MAC_DINH_THU_VIEN } from "@/lib/libraryQuery";
import { fandomCauTruc } from "@/lib/taxonomy";
import { isLegacyAudioOnly, novelHasAudio } from "@/lib/catalog";

/** Khi anh chup loi: bon fandom da co truyen that tai thoi diem viet. */
const DU_PHONG = ["Naruto", "One Piece", "Detective Conan", "Genshin Impact"];

export function FandomStrip() {
  const kho = useAsyncData(taiAnhChupKho);
  const chips = kho.data?.novels.length
    ? chipFandom(
        kho.data.novels,
        fandomCauTruc,
        (n) => ({ cu: isLegacyAudioOnly(n), audio: novelHasAudio(n), status: n.status }),
        MAC_DINH_THU_VIEN,
      )
    : null;

  if (kho.loading) {
    return (
      <div className="story-tags" aria-hidden="true">
        {[88, 72, 120, 110].map((w) => (
          <span key={w} className="sk" style={{ width: w, height: 32, borderRadius: 999 }} />
        ))}
      </div>
    );
  }

  const ds = chips ?? DU_PHONG.map((ten) => ({ ten, so: 0 }));
  return (
    <div className="story-tags" aria-label="Vũ trụ fanfic">
      {ds.map((c) => (
        <Link
          key={c.ten}
          href={`/library?fandom=${encodeURIComponent(c.ten)}`}
          className="chip fandom-strip-chip"
          prefetch={false}
        >
          {c.ten}
          {c.so > 0 ? <span className="fandom-strip-so">{c.so}</span> : null}
        </Link>
      ))}
      <Link href="/library" className="chip fandom-strip-chip" prefetch={false}>
        Tất cả truyện →
      </Link>
    </div>
  );
}
