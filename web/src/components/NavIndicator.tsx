"use client";

/**
 * MOT vien thuoc dung chung cho ca thanh dieu huong.
 *
 * VAN DE DA CO: moi muc tu ve nen/vach cua rieng no. Doi trang thi cai o muc cu
 * BIEN MAT va mot cai moi XUAT HIEN o muc khac. Khong co gi noi hai trang thai
 * voi nhau, nen mat khong doc ra "toi vua di tu day sang kia" — chi doc ra "co
 * gi vua nhap nhay".
 *
 * CACH LAM: mot phan tu duy nhat, `position: absolute` trong thanh, TRUOT tu o
 * cu sang o moi bang `transform` + `width`.
 *
 * ==========================================================================
 * BA quyet dinh kien truc, va ly do cua tung cai:
 *
 * 1. DO TU MOT BANG THAM CHIEU, khong tu `querySelector`.
 *
 *    Ban truoc tim muc dang xem bang `[aria-current="page"]`, roi bang
 *    `a[href=...]`. Ca hai deu doc TRANG THAI DOM, va trang thai do do React
 *    cap nhat o mot lan ve co the den sau. Mot bang `href -> phan tu` do chinh
 *    cac muc tu dang ky thi khong con gi de doi.
 *
 * 2. `useLayoutEffect`, khong phai `useEffect` + `requestAnimationFrame`.
 *
 *    `useLayoutEffect` chay NGAY SAU khi React gan DOM va TRUOC khi trinh duyet
 *    ve. Vien thuoc dung cho ngay o khung hinh dau tien — khong bao gio co mot
 *    khung nao no con o cho cu.
 *
 *    `requestAnimationFrame` co mot diem yeu that: no CHI chay khi trang duoc
 *    ve. Trong mot tab bi an, hoac trong mot phien do tu dong giu chan luong
 *    chinh, callback do khong bao gio chay va vien thuoc dung yen.
 *
 *    Chinh dieu do da lam toi tuong nham co mot loi "tre mot nhip dieu huong":
 *    phep do cua toi chay trong mot vong lap dai, bo doi rAF, roi doc lai ket
 *    qua cua chinh no. Do bang nhung lenh goi TACH ROI thi vien thuoc luon dung.
 *
 * 3. `ResizeObserver` cho phan CON LAI.
 *
 *    Chu tai xong muon, doi be rong cua so, hay hang bi cuon o mobile deu lam
 *    hinh hoc doi SAU khi ve. Mot bo quan sat bat dung nhung luc do; mot vong
 *    lap kiem tra lien tuc thi chay mai ma phan lon thoi gian khong co gi doi.
 * ==========================================================================
 */

import { useLayoutEffect, useState } from "react";
import { viTri } from "@/lib/sections";

/** Bang `href -> phan tu`, do chinh cac muc dieu huong tu dang ky. */
export type BangMuc = Map<string, HTMLElement>;

type O = {
  /**
   * `href` ma phep do nay thuoc ve.
   *
   * Co mat de render biet ket qua da la CUA ROUTE HIEN TAI hay con la cua route
   * truoc. Nho vay khong can mot `setState` dong bo trong than effect de xoa
   * trang thai cu — dieu ma quy tac `react-hooks/set-state-in-effect` cam, va
   * cam co ly: mot `setState` trong than effect tao them mot vong ve.
   */
  moc: string;
  x: number;
  w: number;
  /** Cao cua hop, do cung luc voi `w` — dung de ve SVG tracer khop kich
   * thuoc that (xem `nav-vach-tracer-stroke`). Khong doc tu CSS: `.nav-vach`
   * dat `height: 34px` co dinh trong CSS, nhung do TRUC TIEP tu DOM giong
   * `w` thay vi lap lai con so do o hai noi la tranh mot nguon lech neu sau
   * nay chieu cao doi. */
  h: number;
  /**
   * Lan do dau tien thi KHONG truot: vao thang `/library` ma thay vien thuoc bo
   * tu "Trang chủ" sang doc ra la mot loi ve, khong phai mot hieu ung.
   *
   * Co nay nam TRONG trang thai chu khong o mot `ref` doc luc render: doc
   * `ref.current` trong than render la thu React khong dam bao.
   */
  truot: boolean;
  /**
   * Dem so lan DOI ROUTE THAT (khong tinh do lai vi resize/cuon o CUNG mot
   * muc). Dung lam `key` cho vet sang mot lan (`.nav-vach-streak`) — doi key
   * thi React go phan tu cu, gan phan tu moi, va animation CSS tren no chay
   * lai tu dau. Khong dung mot bien dem ngoai state (vi du `useRef`) vi gia
   * tri do phai co mat trong LAN RENDER dung key, va doc `ref.current` trong
   * than render khong duoc dam bao boi React.
   */
  tick: number;
};

export function NavIndicator({
  bao,
  bang,
  moc,
}: {
  /** Phan tu bao cac muc. Phai co `position: relative`. */
  bao: React.RefObject<HTMLElement | null>;
  /** Bang tham chieu cua cac muc. Xem ghi chu 1 o dau tep. */
  bang: React.RefObject<BangMuc>;
  /**
   * `href` cua muc DANG XEM, hoac chuoi rong khi khong muc nao khop.
   *
   * NGUON SU THAT la duong dan: nguoi goi suy ra tu `pathname` roi truyen
   * xuong. Khong doc nguoc lai tu DOM.
   */
  moc: string;
}) {
  const [o, setO] = useState<O | null>(null);

  useLayoutEffect(() => {
    /*
      DOC `bao.current` BEN TRONG `do_lai`, khong o than effect.

      React gan ref TU DUOI LEN: `NavIndicator` la con cua the `<nav>`, nen o
      lan commit dau tien, layout effect cua no chay TRUOC khi ref cua `<nav>`
      cha duoc gan. Ban truoc doc `bao.current` ngay o than effect, thay `null`,
      va thoat som — roi khong bao gio chay lai vi cac phu thuoc khong doi.

      Trieu chung: dieu huong bang chuot thi vien thuoc dung, nhung TAI THANG
      `/library` thi no khong hien ra chut nao. Da do duoc tren trinh duyet.

      Vi tac vu va callback cua `ResizeObserver` deu chay SAU khi ca cay da
      commit xong, nen luc do `bao.current` chac chan da co.
    */
    const do_lai = () => {
      const hop = bao.current;
      const muc = moc ? bang.current.get(moc) : undefined;
      /*
        Trang khong co muc nao khop (`/login`, `/admin`, `/u/*`): khong do gi ca.
        Trang thai cu o lai, nhung `o.moc !== moc` nen render tra `null` — vien
        thuoc bien mat ma khong can mot `setState` trong than effect.
      */
      if (!hop || !muc) return;

      const a = hop.getBoundingClientRect();
      const b = muc.getBoundingClientRect();
      /*
        Cong `scrollLeft`: o mobile hang nay cuon ngang duoc, va
        `getBoundingClientRect` tra toa do so voi KHUNG NHIN. Khong cong thi
        vien thuoc lech dung bang khoang da cuon.
      */
      const x = b.left - a.left + hop.scrollLeft;
      const w = b.width;
      const h = b.height;
      setO((truoc) => {
        if (truoc && truoc.moc === moc
            && Math.abs(truoc.x - x) < 0.5 && Math.abs(truoc.w - w) < 0.5
            && Math.abs(truoc.h - h) < 0.5) {
          // Khong doi gi — dung tao mot lan ve thua. `ResizeObserver` co the
          // phat vai lan lien tuc khi chu vua tai xong.
          return truoc;
        }
        // `truot` chi bat tu lan do THU HAI tro di — xem `O.truot`.
        const truot = truoc !== null;
        /*
          `tick` CHI tang khi MUC dang xem thuc su doi (dieu huong that) — KHONG
          tang khi cung mot muc do lai vi resize/cuon (`truoc.moc === moc` da bi
          chan o nhanh tren NEU vi tri khong doi; nhung chu tai xong muon van co
          the lam CUNG mot muc do ra vi tri khac, va do khong phai mot lan dieu
          huong). Neu tang ca luc do thi vet sang phat lai moi khi ai do resize
          cua so — sai voi dung y "MOT lan, dung luc doi trang".
        */
        const tick = truoc && truoc.moc !== moc ? truoc.tick + 1 : (truoc?.tick ?? 0);
        return { moc, x, w, h, truot, tick };
      });
    };

    /*
      KHONG goi `do_lai()` thang trong than effect: do la mot `setState` dong bo,
      va quy tac `react-hooks/set-state-in-effect` cam dieu do.

      Khong can goi that: `ResizeObserver` phat NGAY mot lan cho moi phan tu
      vua duoc quan sat, va callback do chay TRUOC khi trinh duyet ve. Nen phep
      do dau tien van kip cho khung hinh dau tien — dung dieu ma
      `useLayoutEffect` duoc chon vi no.

      Quan sat CA cai bao lan chinh muc dang xem. Mot minh cai bao la khong du:
      chu tai xong muon lam MUC rong ra trong khi bao giu nguyen be rong.
    */
    /*
      LUON dat mot phep do o nhip vi mo tiep theo.

      Ban truoc trong cay vao lan phat dau tien cua `ResizeObserver`, va do la
      SAI — do duoc tren trinh duyet: tai thang `/library` thi vien thuoc khong
      hien ra chut nao. Lan phat do khong dang tin cay lam phep do khoi tao.

      Mot vi tac vu thi chac chan chay, chay TRUOC khi trinh duyet ve, va khong
      phai la mot `setState` dong bo trong than effect — nen quy tac
      `react-hooks/set-state-in-effect` van hai long.
    */
    queueMicrotask(do_lai);

    const hop = bao.current;
    const muc = moc ? bang.current.get(moc) : undefined;
    const ro =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(do_lai);
    if (ro && hop) ro.observe(hop);
    if (ro && muc) ro.observe(muc);
    hop?.addEventListener("scroll", do_lai, { passive: true });

    return () => {
      ro?.disconnect();
      hop?.removeEventListener("scroll", do_lai);
    };
  }, [bao, bang, moc]);

  /*
    `o.moc !== moc` nghia la phep do dang co la CUA ROUTE TRUOC — trang hien tai
    khong co muc nao trong thanh dieu huong. An vien thuoc di.
  */
  if (!o || o.moc !== moc) return null;

  return (
    <span
      className="nav-vach"
      aria-hidden="true"
      data-dung-yen={o.truot ? undefined : ""}
      style={{
        transform: `translateX(${o.x}px)`,
        width: `${o.w}px`,
        /*
          `height`/`marginTop` DONG BO voi `o.h` do duoc, cung ly do va cung
          co che voi `width` o tren — thieu dong bo nay la mot loi HINH HOC
          THAT (phat hien qua review doc lap 2026-08-23): `.nav-vach` dat
          `height: 34px` co dinh trong CSS, nhung `o.h` do tu `.nav-link`
          (bao gom padding/border cua CHINH muc, vd 36-38px tuy muc) THUONG
          KHONG BANG 34. SVG tracer dung `viewBox={0 0 o.w o.h}` +
          `preserveAspectRatio="none"` — hop thuc te (34px, tu CSS) va he
          truc SVG (o.h, tu JS) khac nhau se ep SVG co GIAN THEO CHIEU DOC
          khong deu, lam net tron o hai dau tracer bi meo thanh hinh elip.
          Ghi de height/marginTop inline (giong width) xoa han su khac biet
          nay — hop THAT SU cao dung `o.h`, khong con hai nguon so lech nhau.
        */
        height: `${o.h}px`,
        marginTop: `${-o.h / 2}px`,
        /*
          Sac cua khu vuc dang toi, truyen qua bien de CSS noi mau muot trong
          luc vien thuoc di chuyen. Dat thang mau vao mot lop se lam mau NHAY o
          dau chuyen dong thay vi chuyen dan.
        */
        ["--sac-1" as string]: `var(--sac-${viTri(moc)}-1, var(--brand))`,
        ["--sac-2" as string]: `var(--sac-${viTri(moc)}-2, var(--brand-hover))`,
      }}
    >
      {/*
        Vet sang "cong dich" — chay MOT LAN doc vien khi vach vua toi noi, xem
        `.nav-vach-streak` (dung lai keyframe `sheen` da co, xem
        `.progress-bar::after`). `key={o.tick}` la co che retrigger: doi key
        thi React thao phan tu nay va gan mot phan tu MOI, nen animation CSS
        tren no luon chay tu dau — khong can mot dong ho JS rieng de "reset"
        animation. Chi ve khi `o.truot` (bo qua lan ve dau tien, xem `O.truot`).
      */}
      {o.truot ? <span key={o.tick} className="nav-vach-streak" aria-hidden="true" /> : null}
      {/*
        Tracer vien — mot doan sang NGAN chay VONG QUANH vien pill LIEN TUC
        trong suot luc muc con duoc chon (khac han vet sang o tren, chi chay
        MOT LAN roi tat). Phuc hoi tu `feature/fanfic-visual-renaissance-v1`
        (V7), dung ky thuat SVG `stroke-dasharray`/`stroke-dashoffset` thay vi
        ban dau (`conic-gradient` xoay + mask) — ban SVG la lua chon CUOI CUNG
        cua nhanh do sau nhieu vong sua, va khong dinh loi "dom mau ket lai"
        tung gap voi ban conic-gradient.

        `pathLength={100}`: chuan hoa don vi stroke ve % chu vi BAT KE kich
        thuoc thuc te cua o (o.w doi theo do dai ten muc) — nho vay
        `stroke-dasharray: 14 86` trong CSS luon nghia la "sang 14%, toi 86%"
        du o hep hay rong, khong can tinh lai theo pixel.

        `rx`/`ry` = h/2 (tru insert) de khop dung bien tron cua `.nav-vach`
        (border-radius: var(--r-full), tuc la BO TRON HOAN TOAN theo chieu
        cao co dinh 34px) — do TRUC TIEP tu `o.h` thay vi hang so, xem ghi chu
        o kieu `O.h`.

        KHONG ve khi giam chuyen dong: xem quy tac
        `prefers-reduced-motion` cho `.nav-vach-tracer-stroke` — an han di,
        chi con vien tinh + nen cua `.nav-vach` de bao "dang chon", dung y
        cau hoi "reduced-motion fallback phai VAN doc ra dang chon ma khong
        chuyen dong".
      */}
      <svg
        className="nav-vach-tracer"
        viewBox={`0 0 ${o.w} ${o.h}`}
        width="100%"
        height="100%"
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <rect
          className="nav-vach-tracer-stroke"
          x={NAV_TRACER_INSET}
          y={NAV_TRACER_INSET}
          width={Math.max(0, o.w - NAV_TRACER_INSET * 2)}
          height={Math.max(0, o.h - NAV_TRACER_INSET * 2)}
          rx={Math.max(0, o.h / 2 - NAV_TRACER_INSET)}
          ry={Math.max(0, o.h / 2 - NAV_TRACER_INSET)}
          pathLength={100}
          fill="none"
        />
      </svg>
    </span>
  );
}

/** Le vao cua stroke tracer so voi mep `.nav-vach` — giu net khong bi
 * `overflow: hidden` cua `.nav-vach` cat mat mep ngoai. */
const NAV_TRACER_INSET = 1.5;
