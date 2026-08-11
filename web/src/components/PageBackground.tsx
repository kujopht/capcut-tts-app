"use client";

/**
 * Lop tranh nen theo tung trang, KEM chuyen canh khi doi route.
 *
 * VAN DE CUA BAN TRUOC: doi route la anh nen doi tuc thi. No doc ra nhu doi
 * hinh nen may tinh, khong phai nhu di qua mot the gioi lien mach.
 *
 * CACH LAM: giu DUNG HAI lop.
 *
 *   lop duoi  tam CU, dang mo dan ra
 *   lop tren  tam MOI, dang hien dan vao
 *
 * Khi `pathname` doi:
 *   1. tra ra tam moi tu bang anh xa;
 *   2. NAP TRUOC bang `new Image()` — chua nap xong thi chua doi gi ca, nen
 *      khong bao gio co mot nhay den giua hai tam;
 *   3. nap xong thi day tam cu xuong lop duoi va cho tam moi hien dan;
 *   4. het chuyen canh thi BO lop cu. Khong bao gio de ba lop chong nhau.
 *
 * CHI hai phan tu, va con so do khong doi theo so lan dieu huong.
 *
 * KHONG lam mo ca ung dung, khong lam mo doan noi dung: thanh dieu huong va noi
 * dung van bam duoc trong suot chuyen canh. Chi hai lop khong khi nay doi.
 *
 * TAB CUC BO khong lam gi o day: `Tất cả / Audio Studio / Fanfic` o Thu vien la
 * trang thai trong mot trang, `pathname` khong doi, nen nen khong nhap nhay.
 *
 * KHONG dung lam bia truyen — do la viec cua `StoryCoverFallback`.
 */

import { useEffect, useRef, useState } from "react";
import { anhNen, tenNen } from "@/lib/backgrounds";
import { huongDi, tenHuong, type Huong } from "@/lib/sections";
import { AmbientScene } from "@/components/AmbientScene";

/** Khop voi `--dur-nen` o `globals.css`. */
const THOI_LUONG = 580;

export function PageBackground() {
  const [duongDan, setDuongDan] = useState<string | null>(null);
  const ten = duongDan === null ? null : tenNen(duongDan);

  /** Tam dang mo dan ra. `null` khi khong co chuyen canh nao dang chay. */
  const [tenCu, setTenCu] = useState<string | null>(null);
  /**
   * Huong cua lan chuyen canh dang chay.
   *
   * Tinh tu HAI DUONG DAN, khong tu hai tam nen: hai duong dan khac nhau co the
   * dung cung mot tam (`/fanfic` va `/novels/x` deu la `explore`), va lay huong
   * tu ten tam se lam moi buoc di vao mot trang truyen thanh "khong co huong".
   */
  const [huong, setHuong] = useState<Huong>(0);
  const truoc = useRef<string | null>(null);
  const duongTruoc = useRef<string | null>(null);
  const hen = useRef<number | null>(null);

  /*
    Doc `location.pathname` thay vi `usePathname()`.

    `usePathname()` buoc component phai o trong cay dieu huong cua Next va se
    ve lai theo moi lan route doi — dung, nhung o day ta con can BIET truoc khi
    doi de nap anh, va can mot cho de don `setTimeout`. Mot `popstate` +
    kiem tra sau moi lan ve lai la du, va no khong dong vao trang thai route.
  */
  useEffect(() => {
    const doc = () => setDuongDan(window.location.pathname);
    doc();
    // Next dieu huong bang History API, khong phat `popstate` khi `pushState`.
    // Theo doi bang mot vong kiem nho — re hon nhieu so voi tai lai anh sai.
    const id = window.setInterval(doc, 120);
    window.addEventListener("popstate", doc);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("popstate", doc);
    };
  }, []);

  useEffect(() => {
    if (!ten || duongDan === null) return;
    if (truoc.current === null) {
      // Lan dau: khong co gi de chuyen canh tu.
      truoc.current = ten;
      duongTruoc.current = duongDan;
      return;
    }
    if (truoc.current === ten) {
      // Cung mot tam nen — vi du `/fanfic` -> `/novels/x`. Khong chuyen canh,
      // nhung VAN phai nho duong dan moi: neu khong thi buoc di tiep theo se
      // tinh huong tu mot duong dan cu da hai lan dieu huong truoc do.
      duongTruoc.current = duongDan;
      return;
    }

    const cu = truoc.current;
    truoc.current = ten;
    const huongMoi = huongDi(duongTruoc.current ?? "/", duongDan);
    duongTruoc.current = duongDan;

    /*
      NAP TRUOC roi moi doi. Neu doi ngay thi trinh duyet ve mot khung trong
      trong luc tai, va nguoi dung thay mot nhay den giua hai tam.

      `decode()` cho ca truong hop anh da nam trong cache: no tra ve ngay, nen
      chuyen canh bat dau lien ma khong phai cho mot vong mang nao.
    */
    let huy = false;
    const img = new Image();
    img.src = anhNen(ten);
    const batDau = () => {
      if (huy) return;
      setHuong(huongMoi);
      setTenCu(cu);
      if (hen.current) window.clearTimeout(hen.current);
      hen.current = window.setTimeout(() => setTenCu(null), THOI_LUONG);
    };
    if (img.decode) img.decode().then(batDau, batDau);
    else img.onload = batDau, img.onerror = batDau;

    return () => {
      huy = true;
    };
  }, [ten, duongDan]);

  useEffect(
    () => () => {
      if (hen.current) window.clearTimeout(hen.current);
    },
    [],
  );

  if (!ten) return null;

  const huongText = tenHuong(huong);

  return (
    <div className="page-bg" aria-hidden="true">
      {/*
        HAI lop, va `data-huong` quyet dinh chung truot ve dau.

        `tien`  may quay sang phai — di sang khu vuc ben phai tren truc
        `lui`   nguoc lai
        `nhe`   chi mo/hien kem mot cu dich rat nho: dung cho trang long
                (`/novels/*`, `/chapters/*`) va cho cac buoc khong co huong

        Bien do nho — 5vw ra, 8vw vao — va do la co y: truot ca man hinh 100vw
        doc ra nhu mot slide PowerPoint, con mot cu dich nho doc ra nhu may vua
        quay sang mot khu khac cua cung mot the gioi.
      */}
      {tenCu ? (
        <div className="page-bg-lop" data-bg={tenCu} data-ra="" data-huong={huongText} />
      ) : null}

      {/* Lop TREN: tam hien hanh. `key` doi theo tam nen hieu ung hien dan tu
          chay lai — khong phai theo doi trang thai gi them. */}
      <div className="page-bg-lop" data-bg={ten} key={ten} data-vao=""
           data-huong={huongText} />

      {/* Hat sang — CSS quyet dinh trang nao ve. Mot phan tu, khong phai vai tram. */}
      <div className="hat" data-bg={ten} />

      {/*
        Khong khi rieng cua tung khu vuc. Dat o DAY chu khong o `layout.tsx`:
        component nay da theo doi `pathname` roi, va them mot cho nua theo doi
        cung mot thu la them mot cho nua co the lech.
      */}
      <AmbientScene duongDan={duongDan ?? "/"} />
    </div>
  );
}
