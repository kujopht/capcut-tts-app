"use client";

/**
 * MOT vach sang dung chung cho ca thanh dieu huong.
 *
 * VAN DE DA CO: moi muc tu ve vach cua rieng no bang `::after`. Doi trang thi
 * vach o muc cu BIEN MAT va mot vach moi XUAT HIEN o muc khac. Khong co gi noi
 * hai trang thai voi nhau, nen mat khong doc ra "toi vua di tu day sang kia" —
 * chi doc ra "co gi vua nhap nhay".
 *
 * CACH LAM: mot phan tu duy nhat, dat `position: absolute` trong thanh, va no
 * TRUOT tu o cu sang o moi. Do vi tri bang `getBoundingClientRect()` roi dat
 * `transform: translateX()` + `width`.
 *
 * VI SAO KHONG DUNG `left`: doi `left` buoc trinh duyet tinh lai bo cuc moi
 * khung. `transform` thi chay tren tang ghep va khong cham vao bo cuc. `width`
 * thi khong tranh duoc — no la thu duy nhat lam vach dai ngan theo do dai chu —
 * nhung mot phan tu 2px cao khong co con nao ben trong thi phep tinh lai do gan
 * nhu bang khong.
 *
 * KHONG lam gi khi dang o trang khong co muc nao khop (vd `/login`): vach an di
 * thay vi ngoi lai o muc cuoi.
 */

import { useEffect, useRef, useState } from "react";

type O = {
  x: number;
  w: number;
  /**
   * Lan do dau tien thi KHONG truot: mot cu truot tu goc trai man hinh vao luc
   * moi mo trang doc ra nhu mot loi ve.
   *
   * Co nay nam TRONG trang thai chu khong o mot `ref` doc luc render: doc
   * `ref.current` trong than render la thu React khong dam bao — no khong tinh
   * la mot phu thuoc, nen ban ve co the dung gia tri cu.
   */
  truot: boolean;
};

export function NavIndicator({
  /** Phan tu bao cac muc. Chi bao co `position: relative`. */
  bao,
  /** Doi khi gia tri nay doi thi do lai — thuong la `pathname`. */
  moc,
}: {
  bao: React.RefObject<HTMLElement | null>;
  moc: string;
}) {
  const [o, setO] = useState<O | null>(null);
  /** Da tung do duoc mot lan chua. Chi doc/ghi TRONG effect. */
  const daDo = useRef(false);

  useEffect(() => {
    const hop = bao.current;
    if (!hop) return;

    const do_lai = () => {
      const muc = hop.querySelector<HTMLElement>('[aria-current="page"]');
      if (!muc) {
        setO(null);
        // Trang khong co muc nao khop (vd `/login`) khong dat lai `daDo`: quay
        // ve mot trang co muc thi vach van truot, khong nhay.
        return;
      }
      const a = hop.getBoundingClientRect();
      const b = muc.getBoundingClientRect();
      /*
        Cong `scrollLeft`: o mobile hang nay cuon ngang duoc, va
        `getBoundingClientRect` tra toa do so voi KHUNG NHIN. Khong cong thi vach
        lech dung bang khoang da cuon.
      */
      setO({
        x: b.left - a.left + hop.scrollLeft,
        w: b.width,
        truot: daDo.current,
      });
      daDo.current = true;
    };

    /*
      Do SAU khi trinh duyet da ve xong. `requestAnimationFrame` chu khong phai
      do ngay trong effect: `aria-current` vua doi o cung mot lan ve, va doc kich
      thuoc ngay lap tuc co the tra ve so cua khung TRUOC.
    */
    const khung = requestAnimationFrame(do_lai);

    /*
      Do lai khi be rong doi. `ResizeObserver` tren chinh cai bao chu khong phai
      `window.resize`: chu tai xong muon cung lam cac muc rong ra, va mot su kien
      `resize` khong bao gio phat trong truong hop do.
    */
    const ro =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(do_lai);
    if (ro) {
      ro.observe(hop);
      for (const con of Array.from(hop.children)) ro.observe(con);
    }

    // Cuon hang o mobile cung lam vach lech — no duoc dat theo toa do trong hang.
    hop.addEventListener("scroll", do_lai, { passive: true });

    return () => {
      cancelAnimationFrame(khung);
      ro?.disconnect();
      hop.removeEventListener("scroll", do_lai);
    };
  }, [bao, moc]);

  if (!o) return null;

  return (
    <span
      className="nav-vach"
      aria-hidden="true"
      data-dung-yen={o.truot ? undefined : ""}
      style={{ transform: `translateX(${o.x}px)`, width: `${o.w}px` }}
    />
  );
}
