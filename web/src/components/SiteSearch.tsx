"use client";

/**
 * O tim kiem trong header.
 *
 * CO Y NHO. Truoc day khong co o tim nao o header, va cach de nhat la dan mot
 * thanh tim khong lo giua trang chu — nhung day la trang de DOC truyen, khong
 * phai cong cu tra cuu. Thanh tim to chiem cho cua thu nguoi doc thuc su can
 * thay: bia va ten truyen.
 *
 * KHONG tu tim. Form nay chi DIEU HUONG sang `/fanfic?q=...`, noi da co san
 * toan bo phan tim/loc/phan trang do BACKEND lam (xem `L2` trong
 * `tests/final-polish.test.mjs`). Nhan ban mot duong tim thu hai o day la cach
 * chac chan de hai ben lech nhau.
 */

import { useEffect, useState } from "react";
import { SearchOverlay } from "@/components/SearchOverlay";

/**
 * O tim o header gio la mot NUT MO overlay, khong con la mot form rieng.
 *
 * Vi sao doi: tu khi co trang ca nhan, mot o chi biet tim truyen se tra loi sai
 * cho mot nua so cau hoi — go ten mot nguoi vao do ra "khong tim thay truyen
 * nao", va nguoi dung khong co cach nao biet minh dang tim sai cho.
 *
 * Ve NHU mot o nhap chu khong nhu mot cai nut: nguoi ta tim mot o de go, va mot
 * cai nut ghi "Tim kiem" thi mat luot qua khong nhan ra.
 */
export function SiteSearch() {
  const [mo, setMo] = useState(false);

  useEffect(() => {
    /*
      Phim tat toan cuc. `/` la quy uoc cua cac trang doc — no khong xung dot voi
      viec go vi ta bo qua khi tieu diem dang o mot o nhap. Ctrl/Cmd+K la quy uoc
      cua cac bang dieu khien; ca hai deu quen tay voi hai nhom nguoi khac nhau.
    */
    const phim = (e: KeyboardEvent) => {
      const dich = e.target as HTMLElement | null;
      const dangGo =
        dich instanceof HTMLInputElement ||
        dich instanceof HTMLTextAreaElement ||
        dich?.isContentEditable;
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setMo(true);
      } else if (e.key === "/" && !dangGo && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setMo(true);
      }
    };
    window.addEventListener("keydown", phim);
    return () => window.removeEventListener("keydown", phim);
  }, []);

  return (
    <>
      <button
        type="button"
        className="site-search tim-nut"
        onClick={() => setMo(true)}
        aria-haspopup="dialog"
      >
        <span className="tim-nut-chu">Tìm truyện, tác giả…</span>
        <kbd className="tim-phim" aria-hidden="true">
          /
        </kbd>
      </button>
      <SearchOverlay mo={mo} onDong={() => setMo(false)} />
    </>
  );
}
