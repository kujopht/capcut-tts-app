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

import { useLayoutEffect, useRef, useState } from "react";
import { viTri } from "@/lib/sections";

/** Bang `href -> phan tu`, do chinh cac muc dieu huong tu dang ky. */
export type BangMuc = Map<string, HTMLElement>;

/**
 * Khoang lang (ms) giu vien rieng cua CTA ("Viết truyện") o trang thai trong
 * suot SAU KHI `aria-current` da mat — xem `[data-nav-leaving="write"]` o
 * globals.css. Phai >= thoi luong `width` cua `.nav-vach` (540ms, thoi gian
 * DAI NHAT trong hai transition hinh hoc) de dam bao vach dung chung da
 * THAT SU roi khoi hinh dang CTA truoc khi vien rieng hien lai — them mot
 * bien nho de khong sat nut.
 */
const CTA_LEAVE_GRACE_MS = 560;

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
  y: number;
  w: number;
  h: number;
  /**
   * Bo goc DICH — V6: doc THANG tu `getComputedStyle(muc).borderTopLeftRadius`
   * cua chinh phan tu dang do, KHONG con qua mot bang tham chieu theo "hinh
   * dang" (`data-nav-shape`/`NAV_RADIUS` cua V5). Ly do doi: hai muc CO THE
   * dung CUNG mot gia tri bo goc (ca hai deu `--r-full`) nhung KHAC chieu
   * cao that (xem `h`) — mot bang tra theo "shape" chi bao dam dung mau,
   * khong bao dam dung KICH THUOC, va chinh sai lech kich thuoc (khong phai
   * bo goc) la nguyen nhan that cua loi "khung nho hon/khac hinh" da phan
   * hoi (do duoc tren staging: `.nav-vach` cao co dinh 32px trong khi CTA
   * "Viết truyện" cao that 38px).
   */
  radius: number;
  /**
   * Lan do dau tien thi KHONG truot: vao thang `/library` ma thay vien thuoc bo
   * tu "Trang chủ" sang doc ra la mot loi ve, khong phai mot hieu ung.
   *
   * Co nay nam TRONG trang thai chu khong o mot `ref` doc luc render: doc
   * `ref.current` trong than render la thu React khong dam bao.
   */
  truot: boolean;
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
  /**
   * Muc dang xem TRUOC co phai CTA hay khong — de nhan ra dung LUC roi CTA
   * (xem `CTA_LEAVE_GRACE_MS`). V6: tach RIENG khoi hinh hoc (`radius`/`h`
   * gio la do THAT, khong con la mot gia tri "theo shape" co the dung de suy
   * nguoc "day co phai CTA khong"). Doc tu `data-nav-cta` — mot CO RIENG,
   * KHONG lien quan gi toi bo goc/kich thuoc do duoc.
   */
  const laCtaTruocRef = useRef(false);
  /** Bo dem cho phep go `data-nav-leaving`, de mot lan roi CTA moi khong bi
   * mot lan roi CTA cu (dieu huong lien tiep, nhanh) go som hon dinh. */
  const heTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    /*
      Neu bo goc VUA do duoc KHAC "cta" trong khi bo goc CU (`radiusTruocRef`)
      LA "cta" — nghia la vach dung chung vua roi hinh dang "Viết truyện" —
      bat `data-nav-leaving="write"` tren <body> trong `CTA_LEAVE_GRACE_MS`
      roi tu go. Xem `[data-nav-leaving="write"]` o globals.css: trong luc co
      la, vien rieng cua CTA van bi giu trong suot du `aria-current` da mat,
      tranh "vien trong vien" khi vach dung chung con dang truot ngang qua/gan
      vi tri cu cua no.
    */
    const bao_roi_cta = (laCta: boolean) => {
      if (laCtaTruocRef.current && !laCta && typeof document !== "undefined") {
        document.body.dataset.navLeaving = "write";
        if (heTimerRef.current) clearTimeout(heTimerRef.current);
        heTimerRef.current = setTimeout(() => {
          delete document.body.dataset.navLeaving;
          heTimerRef.current = null;
        }, CTA_LEAVE_GRACE_MS);
      }
      laCtaTruocRef.current = laCta;
    };

    const do_lai = () => {
      const hop = bao.current;
      const muc = moc ? bang.current.get(moc) : undefined;
      /*
        SUA (Navigation Motion Correction V3): truoc day nhanh nay CHI
        `return` — bo qua, khong dong `o`. Ket qua: hinh hoc CU (vi du "Viết
        truyện") nam yen trong state trong suot ca luc trang khong co muc nao
        active that su (`/login` khong `next=` hop le), roi khi mot muc MOI
        xuat hien, no "hien lai tu vi tri an cu" thay vi xuat hien thang tai
        dich — dung nhu phan hoi da ghi nhan ("tai xuat hien tu vi tri Viết
        truyện cu").

        `moc` rong (khong phai chi thieu `muc`) nghia la trang NAY THAT SU
        khong co gi active — xoa sach `o` de lan xuat hien tiep theo la mot
        phep do DAU TIEN (`truot` se la `false`, xem `O.truot`), tuc la XUAT
        HIEN THANG tai dich, khong truot tu hinh hoc an cu.

        Khi `moc` co gia tri nhung CHUA tim thay `muc` (khung hinh dau tien
        truoc khi cac Link kip dang ky vao `bang`) thi GIU NGUYEN `o` — day
        chi la chua do KIP, khong phai "khong co gi active".
      */
      if (!moc) {
        bao_roi_cta(false);
        setO((truoc) => (truoc === null ? truoc : null));
        return;
      }
      if (!hop || !muc) return;

      const a = hop.getBoundingClientRect();
      const b = muc.getBoundingClientRect();
      /*
        Cong `scrollLeft`: o mobile hang nay cuon ngang duoc, va
        `getBoundingClientRect` tra toa do so voi KHUNG NHIN. Khong cong thi
        vien thuoc lech dung bang khoang da cuon.

        V6: do CA `y`/`h` — khong con dung `top:50%; height:32px` co dinh cua
        `.nav-vach` (gia dinh MOI muc cao bang nhau, SAI voi "Viết truyện":
        do duoc tren staging la 38.14px trong khi cac muc thuong ~36px, va
        vien thuoc cu ghim cung 32px). Do THAT tung muc thi khop duoc VOI
        MOI chieu cao, khong can biet truoc muc nao cao hon.
      */
      const x = b.left - a.left + hop.scrollLeft;
      const y = b.top - a.top;
      const w = b.width;
      const h = b.height;
      /*
        Bo goc: doc THANG tu CSS da tinh cua chinh phan tu — khong con bang
        tra "hinh dang". `borderTopLeftRadius` dai dien vi ca `.nav-link` lan
        `.nav-cta` deu dung mot gia tri DONG DEU bon goc (`--r2`/`--r-full`
        qua shorthand `border-radius`), khong co goc lech rieng.
      */
      const radius = parseFloat(getComputedStyle(muc).borderTopLeftRadius) || 0;
      const laCta = muc.dataset.navCta !== undefined;
      bao_roi_cta(laCta);
      setO((truoc) => {
        if (truoc && truoc.moc === moc
            && Math.abs(truoc.x - x) < 0.5 && Math.abs(truoc.y - y) < 0.5
            && Math.abs(truoc.w - w) < 0.5 && Math.abs(truoc.h - h) < 0.5
            && truoc.radius === radius) {
          // Khong doi gi — dung tao mot lan ve thua. `ResizeObserver` co the
          // phat vai lan lien tuc khi chu vua tai xong.
          return truoc;
        }
        // `truot` chi bat tu lan do THU HAI tro di — xem `O.truot`.
        const truot = truoc !== null;
        return { moc, x, y, w, h, radius, truot };
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
      /*
        KHONG `clearTimeout(heTimerRef.current)` o day: cleanup nay chay lai
        o MOI lan `moc` doi (moi lan dieu huong), khong chi luc unmount that.
        Neu doi huong hai lan lien tiep trong vong `CTA_LEAVE_GRACE_MS`, don
        don nay se xoa dong ho dang cho MA KHONG chay callback cua no — ket
        qua la `data-nav-leaving="write"` ket dinh mai tren <body> vi khong
        con gi go no. `bao_roi_cta` da tu quan ly viec huy/dat lai dong ho
        moi lan can, nen khong can don o day.
      */
    };
  }, [bao, bang, moc]);

  /*
    SUA LOI GOC (Navigation Motion Correction V2): ban truoc kiem tra
    `o.moc !== moc` de an vien thuoc o trang khong co muc nao khop — nhung
    `moc` (prop) doi NGAY khi route doi, con `o.moc` (state) chi bat kip SAU
    khi layout effect do lai xong. Giua hai thoi diem do, dieu kien tren
    THANG (`o.moc` van la route CU) va component tra `null` — React GO HAN
    the `<span class="nav-vach">`. Layout effect roi setO() gia tri MOI, ve
    lai, mount MOT the <span> HOAN TOAN MOI tai vi tri dich. Transition CSS
    khong bao gio co co hoi chay: no can HAI khung hinh da ve tren CUNG MOT
    phan tu de noi suy, ma o day phan tu bi thao roi gan lai truoc khi trinh
    duyet kip ve khung nao ca — nguoi dung chi thay "vach cu bien mat, vach
    moi xuat hien tai cho khac", dung nhu phan hoi da ghi nhan.

    CACH SUA: chi an vien thuoc khi CHINH `moc` (route hien tai) rong — day
    la truong hop THAT su khong co muc nao de danh dau (`/login`, `/admin`,
    `/u/*`). Con lai LUON ve THE <span> DUY NHAT bang toa do MOI NHAT da do
    (`o.x`/`o.w`), du `o.moc` co tam thoi chua kip khop `moc` hay khong — the
    nay khong bao gio bi thao/gan lai giua hai lan dieu huong, nen transition
    `transform`/`width` co CA HAI khung hinh (cu va moi) tren CUNG MOT phan
    tu de trinh duyet noi suy that.
  */
  if (!moc || !o) return null;

  return (
    <span
      className="nav-vach"
      aria-hidden="true"
      data-dung-yen={o.truot ? undefined : ""}
      style={{
        /*
          V6: `translate(x, y)` thay vi chi `translateX` — vi tri DOC gio
          cung la mot gia tri DO duoc (xem `O.y`), khong con suy tu
          `top:50%; margin-top:-16px` co dinh tren `.nav-vach` (gia dinh MOI
          muc cao bang nhau — sai voi CTA). `transform` (khong phai `top`)
          de tranh reflow, dung tinh than "khong hoat hinh bang layout" cu.
        */
        transform: `translate(${o.x}px, ${o.y}px)`,
        width: `${o.w}px`,
        height: `${o.h}px`,
        /*
          Bo goc DICH (V5, "shape morph"; V6: gia tri gio la DO THAT tu chinh
          phan tu) — chuyen dan cung nhip voi `transform`/`width`/`height`
          (xem `transition` cua `.nav-vach`), khong nhay cung.
        */
        borderRadius: `${o.radius}px`,
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
        SUA (Nav Indicator Reset V4): BO HAN ca khung tracer conic-gradient +
        mask (Phase V3) LAN vet sang mot lan `.nav-vach-streak` (V1) — ca hai
        deu la "hoa vao mot lop nen" chu khong phai "mot net ve". Nguyen nhan
        goc cua quang mau bi phan hoi: `.nav-vach-streak` chay animation MOT
        LAN nhung KHONG dat `animation-fill-mode: forwards`; het 480ms, thuoc
        tinh `transform` quay ve gia tri tac gia (khong co, tuc `none`) thay
        vi dung yen o cuoi keyframe — mot khoi gradient `inset:0` (PHU KIN
        long trong) dung yen tai `transform: none` chinh la vung mau xanh
        lam/tim ma nguoi dung thay "dinh vao" ben trong khung.

        THAY BANG SVG: `fill="none"` tren CA HAI <rect> nghia la KHONG BAO
        GIO co mot lop mau phu long trong — chi mot net 1-1.5px doc theo chu
        vi. Day la ly do kien truc nay khong the tai dien loi tren du code co
        sai o dau: khong co thuoc tinh nao (`fill`, `background`) co the vo
        tinh "phu day" mot vung.
      */}
      <svg
        className="nav-vach-svg"
        width="100%"
        height="100%"
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        {/*
          `x`/`y`/`width`/`height` bang KHONG inset — SVG `calc()` trong
          thuoc tinh XML khong dang tin cay tren moi trinh duyet. Net ve
          (`stroke`) mac dinh nam GIUA duong path (mot nua trong, mot nua
          ngoai hop), nen mot net 1-1.5px se chi lo ra ngoai ~0.5-0.75px —
          khong dang ke, va `.nav-vach` KHONG con `overflow: hidden` (chi
          can cho tracer/vet sang cu, ca hai da bi go) nen khong co gi cat no.
        */}
        {/*
          `rx`/`ry` DAT QUA CSS (`style.rx`), KHONG qua thuoc tinh XML tinh —
          day la ly do CHINH cua Reset V5: `rx` la mot presentation property
          co the CHUYEN DAN bang CSS `transition` (xem `.nav-vach-base-stroke`,
          `.nav-vach-tracer-stroke`), trong khi doi thuoc tinh XML thuan tuy
          nhay tuc thi. Dong bo VOI `o.radius` — CUNG mot gia tri, cung luc
          voi `border-radius` cua `.nav-vach` (Phan 8: "mot ban sac dung
          chung"), khong tinh rieng.
        */}
        {/* LOP A — vien tinh, khong hoat hinh vi tri (chi doi rx theo morph). */}
        <rect
          className="nav-vach-base-stroke"
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="none"
          style={{ rx: `${o.radius}px`, ry: `${o.radius}px` } as React.CSSProperties}
        />
        {/* LOP B — tracer: MOT doan ngan chay quanh chu vi, dung yen sau khi
            dung (`data-dung-yen`) hoac duoi prefers-reduced-motion (CSS). */}
        <rect
          className="nav-vach-tracer-stroke"
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="none"
          pathLength="100"
          style={{ rx: `${o.radius}px`, ry: `${o.radius}px` } as React.CSSProperties}
        />
      </svg>
    </span>
  );
}
