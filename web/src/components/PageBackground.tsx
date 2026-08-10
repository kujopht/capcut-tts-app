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

/** Khop voi `--dur-nen` o `globals.css`. */
const THOI_LUONG = 420;

export function PageBackground() {
  const [duongDan, setDuongDan] = useState<string | null>(null);
  const ten = duongDan === null ? null : tenNen(duongDan);

  /** Tam dang mo dan ra. `null` khi khong co chuyen canh nao dang chay. */
  const [tenCu, setTenCu] = useState<string | null>(null);
  const truoc = useRef<string | null>(null);
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
    if (!ten) return;
    if (truoc.current === null) {
      // Lan dau: khong co gi de chuyen canh tu.
      truoc.current = ten;
      return;
    }
    if (truoc.current === ten) return;   // cung mot tam — vi du /fanfic -> /novels

    const cu = truoc.current;
    truoc.current = ten;

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
      setTenCu(cu);
      if (hen.current) window.clearTimeout(hen.current);
      hen.current = window.setTimeout(() => setTenCu(null), THOI_LUONG);
    };
    if (img.decode) img.decode().then(batDau, batDau);
    else img.onload = batDau, img.onerror = batDau;

    return () => {
      huy = true;
    };
  }, [ten]);

  useEffect(
    () => () => {
      if (hen.current) window.clearTimeout(hen.current);
    },
    [],
  );

  if (!ten) return null;

  return (
    <div className="page-bg" aria-hidden="true">
      {/* Lop DUOI: tam cu, mo dan ra. Chi ton tai trong luc chuyen canh. */}
      {tenCu ? <div className="page-bg-lop" data-bg={tenCu} data-ra="" /> : null}

      {/* Lop TREN: tam hien hanh. `key` doi theo tam nen hieu ung hien dan tu
          chay lai — khong phai theo doi trang thai gi them. */}
      <div className="page-bg-lop" data-bg={ten} key={ten} data-vao="" />

      {/* Hat sang — CSS quyet dinh trang nao ve. Mot phan tu, khong phai vai tram. */}
      <div className="hat" data-bg={ten} />
    </div>
  );
}
