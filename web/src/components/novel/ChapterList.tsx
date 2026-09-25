"use client";

/**
 * MUC LUC trang truyen (Product UX Sprint 2).
 *
 * - Tim chuong theo SO hoac TEN, khong phan biet dau ("tai ngo" khop "Tái Ngộ").
 * - Dao thu tu cu -> moi / moi -> cu. CHI DAO NGUOC thu tu backend tra ve,
 *   KHONG tu sap lai theo tieu chi rieng (quy tac o `tests/m3-m4.test.mjs`:
 *   trang khong duoc tu sap lai danh sach chuong).
 * - Danh dau chuong DANG doc (kem %) va chuong DA doc, tu tien do luu tren
 *   trinh duyet (`lib/readerSession.ts`); nut "Tới chương đang đọc".
 * - Moi hang: so thu tu, ten, tien do, "Đọc", va "Nghe" khi co audio. Ban
 *   truoc moi hang co mot nut TIM DAC "Nghe" — 99 nut tim canh nhau thi khong
 *   con nut nao noi bat; nay "Nghe" la nut vien.
 * - 500+ chuong: `content-visibility: auto` tren hang khi muc luc > 150 dong
 *   (trinh duyet bo qua bo cuc/ve cua hang ngoai man hinh), khong can thu
 *   vien ao hoa.
 */

import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { IconArrowDown, IconArrowUp, IconBook, IconHeadphones, IconSearch } from "@/components/Icons";
import { useReaderProgress } from "@/lib/useReaderProgress";
import { chuanHoaTim } from "@/lib/libraryQuery";
import { daXong } from "@/lib/novelProgress";
import type { BanGhiTienDo } from "@/lib/readerSession";
import { formatNumber } from "@/lib/format";

export interface ChuongMucLuc {
  chapter_id: string;
  title: string;
  char_count: number;
  has_audio?: boolean;
  audio_outdated?: boolean;
}

/** Tim/dao chi dang hien khi muc luc dai hon chung nay chuong. */
const HIEN_CONG_CU_TU = 8;
/** Tu chung nay hang tro len moi bat `content-visibility` (xem globals.css). */
const MUC_LUC_DAI = 150;

function tiLe(r: BanGhiTienDo): number | null {
  if (r.thoiLuong > 0 && r.giay > 0) return Math.min(1, r.giay / r.thoiLuong);
  if (r.tongDoan > 0) return Math.min(1, (r.doan + 1) / r.tongDoan);
  return null;
}

export function ChapterList({
  novelId,
  chapters,
}: {
  novelId: string;
  chapters: ChuongMucLuc[];
}) {
  const [tim, setTim] = useState("");
  const [moiTruoc, setMoiTruoc] = useState(false);
  const banGhi = useReaderProgress();
  const hopDs = useRef<HTMLOListElement>(null);

  // Tien do theo chuong CUA TRUYEN NAY (ban ghi xep moi -> cu).
  const tienDo = useMemo(() => {
    const m = new Map<string, BanGhiTienDo>();
    for (const r of banGhi) if (r.novelId === novelId && !m.has(r.chapterId)) m.set(r.chapterId, r);
    return m;
  }, [banGhi, novelId]);
  const dangDocId = useMemo(() => {
    for (const r of banGhi) if (r.novelId === novelId) return r.chapterId;
    return null;
  }, [banGhi, novelId]);

  // Giu SO THU TU goc (vi tri trong danh sach backend) — khong doi khi loc/dao.
  const coSo = useMemo(() => chapters.map((chapter, i) => ({ chapter, so: i + 1 })), [chapters]);
  const hienThi = useMemo(() => {
    const kim = chuanHoaTim(tim);
    let ds = coSo;
    if (kim) {
      const laSo = /^\d+$/.test(kim);
      ds = coSo.filter(
        ({ chapter, so }) => (laSo && String(so).startsWith(kim)) || chuanHoaTim(chapter.title).includes(kim),
      );
    }
    return moiTruoc ? [...ds].reverse() : ds;
  }, [coSo, tim, moiTruoc]);

  const toiChuongDangDoc = () => {
    if (!dangDocId) return;
    setTim("");
    // Doi mot nhip: bo loc vua xoa, hang can ve lai truoc khi cuon toi.
    window.setTimeout(() => {
      const hang = hopDs.current?.querySelector<HTMLElement>(`[data-chuong="${dangDocId}"]`);
      hang?.scrollIntoView({ block: "center", behavior: "smooth" });
      hang?.querySelector<HTMLElement>("a")?.focus({ preventScroll: true });
    }, 30);
  };

  const congCu = chapters.length >= HIEN_CONG_CU_TU;

  return (
    <div className="chapter-list">
      {congCu || dangDocId ? (
        <div className="chapter-tools" role="search">
          {congCu ? (
            <label className="chapter-search">
              <IconSearch size={15} className="chapter-search-icon" />
              <span className="sr-only">Tìm chương</span>
              <input
                type="search"
                value={tim}
                onChange={(e) => setTim(e.target.value)}
                placeholder={`Tìm trong ${chapters.length} chương — số hoặc tên`}
                autoComplete="off"
                enterKeyHint="search"
              />
            </label>
          ) : null}
          {congCu ? (
            <button
              type="button"
              className="btn btn-sm btn-ghost chapter-order"
              onClick={() => setMoiTruoc((x) => !x)}
              aria-label={moiTruoc ? "Đang xếp mới nhất trước. Đổi sang cũ nhất trước" : "Đang xếp cũ nhất trước. Đổi sang mới nhất trước"}
            >
              {moiTruoc ? <IconArrowUp size={15} /> : <IconArrowDown size={15} />}
              {moiTruoc ? "Mới → cũ" : "Cũ → mới"}
            </button>
          ) : null}
          {dangDocId ? (
            <button type="button" className="btn btn-sm btn-outline chapter-jump" onClick={toiChuongDangDoc}>
              Tới chương đang đọc
            </button>
          ) : null}
        </div>
      ) : null}

      {hienThi.length === 0 ? (
        <p className="chapter-empty hint" role="status">
          Không có chương nào khớp “{tim}”.{" "}
          <button type="button" className="novel-desc-toggle" onClick={() => setTim("")}>
            Xoá tìm kiếm
          </button>
        </p>
      ) : (
        <ol ref={hopDs} className={`list list-gon chapter-rows${hienThi.length > MUC_LUC_DAI ? " is-long" : ""}`}>
          {hienThi.map(({ chapter, so }) => {
            const r = tienDo.get(chapter.chapter_id);
            const xong = r ? daXong(r) : false;
            const dang = chapter.chapter_id === dangDocId && !xong;
            const pct = r && dang ? tiLe(r) : null;
            return (
              // KHONG boc ca hang trong <Link>: the <a> khong duoc chua <a>
              // khac. Tieu de la lien ket (trang Doc), cac nut la anh em.
              <li
                key={chapter.chapter_id}
                data-chuong={chapter.chapter_id}
                className={`list-item chapter-row${dang ? " is-current" : ""}${xong ? " is-done" : ""}`}
              >
                <span className="list-index" aria-hidden="true">
                  {so}
                </span>
                <span className="stack-2 list-main">
                  <Link href={`/chapters/${chapter.chapter_id}`} className="truncate list-title">
                    {chapter.title}
                  </Link>
                  <span className="hint chapter-meta">
                    {dang ? (
                      <span className="chapter-state is-current">
                        Đang đọc{pct !== null ? ` · ${Math.max(1, Math.round(pct * 100))}%` : ""}
                      </span>
                    ) : xong ? (
                      <span className="chapter-state is-done">✓ Đã đọc</span>
                    ) : null}
                    <span>{formatNumber(chapter.char_count)} ký tự</span>
                  </span>
                </span>

                <span className="list-actions">
                  <Link
                    className="btn btn-sm btn-ghost"
                    href={`/chapters/${chapter.chapter_id}${dang ? "?mode=read&resume=1" : ""}`}
                    aria-label={`Đọc ${chapter.title}`}
                  >
                    <IconBook size={15} /> <span className="chapter-btn-label">Đọc</span>
                  </Link>
                  {chapter.has_audio ? (
                    <>
                      {/* M4: audio con nghe duoc, chi la co the khong khop
                          noi dung moi nhat. Noi ro thay vi im lang. */}
                      {chapter.audio_outdated ? (
                        <span
                          className="badge badge-warn"
                          title="Chương đã sửa sau khi tạo audio — audio có thể không còn khớp"
                        >
                          <span aria-hidden="true">⚠</span> Audio cũ
                        </span>
                      ) : null}
                      <Link
                        className="btn btn-sm btn-outline"
                        href={`/chapters/${chapter.chapter_id}?mode=listen${dang ? "&resume=1" : ""}`}
                        aria-label={`Nghe ${chapter.title}`}
                      >
                        <IconHeadphones size={15} /> <span className="chapter-btn-label">Nghe</span>
                      </Link>
                    </>
                  ) : null}
                  {/*
                    KHONG co nhan "Chưa có audio" tren tung hang: lap lai 99 lan
                    trong mot muc luc thi la nhieu, va trong nhu mot nut bi khoa.
                    Vang mat nut "Nghe" da noi dung dieu do.
                  */}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
