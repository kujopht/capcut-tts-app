"use client";

/**
 * LiveBackground — Live Wallpaper V1 (kien truc, xem
 * `docs/design/LIVE_WALLPAPER_MANIFEST.md` cho boi canh day du).
 *
 * NGUYEN TAC (khong doi):
 *
 *   1. `poster` (anh tinh) LUON la be mat DAU TIEN, tai NGAY, khong bao gio
 *      cho video moi ve mat gi ca — day la ly do component KHONG chan
 *      render dau tien tren video (khong anh huong LCP).
 *   2. Video CHI hien khi THAT SU san sang phat (`onCanPlay`), va hien bang
 *      mot lan crossfade opacity — khong bao gio co mot khung trong/den
 *      truoc do, khong bao gio nhay hinh.
 *   3. Loi tai video (`onError`) -> quay ve CHI con poster, vinh vien cho
 *      lan render nay — khong thu lai, khong hien loi ra nguoi dung (day
 *      la trang tri nen, khong phai noi dung).
 *   4. TON TRONG `prefers-reduced-motion: reduce`, `navigator.connection.
 *      saveData`, va trang thai an/hien cua tab — video KHONG duoc phat khi
 *      nguoi dung khong muon chuyen dong, dang tiet kiem du lieu, hoac tab
 *      dang o nen.
 *   5. KHONG Canvas, KHONG WebGL, KHONG vong lap `requestAnimationFrame`
 *      trang tri — chi mot the `<video>` HTML5 chuan, dieu khien bang su
 *      kien (`canplay`/`error`/`visibilitychange`), khong phai vong lap.
 *
 * V2 (xem bao cao review Candidate A): video toan khung bi tu choi — camera
 * zoom dan du duoc yeu cau khoa cung, va 720p AI mo hon anh tinh goc. Them
 * `videoMask` (tuy chon): mot anh mask CSS (`mask-image`) de video CHI hien
 * qua nhung vung duoc chon (may/nuoc/la) — kien truc "hybrid cinemagraph".
 * Anh tinh goc luon la lop DUOI CUNG, sac net toan bo; video KHONG BAO GIO
 * thay the toan khung nua khi co `videoMask`.
 *
 * V3 — SUA LOI "keo cua so qua man hinh khac lam mat video vinh vien":
 *
 * HAI KHAI NIEM phai tach BACH, day la goc cua loi:
 *
 *   DU DIEU KIEN (`choPhep`)   video co duoc PHEP ton tai hay khong — chi
 *                              phu thuoc `prefers-reduced-motion`, Save-Data,
 *                              be rong khung nhin (CSS `max-width`), va
 *                              `mobileVideo`. KHONG BAO GIO phu thuoc
 *                              `window.blur`/`focus`, `devicePixelRatio`,
 *                              hay `screen.width/height`.
 *   TRANG THAI PHAT (`sanSang`/`loi`) video co dang chay hay khong NGAY LUC
 *                              nay — tam dung khi tab an, phat tiep khi tab
 *                              hien; day la chuyen dong TAM THOI, khong bao
 *                              gio duoc phep ha `choPhep`.
 *
 * Loi cu: `onError` coi MOI loi la vinh vien (`setLoi(true)`, "khong thu
 * lai" — dung dac ta ban dau). Nhung keo cua so trinh duyet giua hai man
 * hinh vat ly khac nhau (khac GPU/khac ty le DPI — pho bien tren laptop co
 * do hoa kep) co the khien Chromium reset ngu canh giai ma cung (GPU
 * context loss) va phat mot su kien `error` THOANG QUA tren `<video>` dang
 * chay — hoan toan khong lien quan gi toi video/URL that su hong. Component
 * cu bat loi do la vinh vien, roi VE LAI vinh vien poster — dung hien tuong
 * da duoc bao cao ("chuyen man hinh thi live wallpaper roi ve tinh mai").
 *
 * SUA: thu TAI LAI dung MOT LAN (`el.load()` + `el.play()`) truoc khi ket
 * luan hong that su. Mot loi that (URL sai, tep hong) se loi LAN HAI ngay
 * sau khi tai lai — luc do moi `setLoi(true)`. Mot loi thoang qua (GPU
 * context) thi lan tai lai thu hai thanh cong, video tiep tuc binh thuong.
 *
 * Loi cu thu hai: hai truy van `matchMedia` (`prefers-reduced-motion`,
 * `max-width: 640px`) chi doc MOT LAN luc mount, khong bao gio cap nhat lai.
 * Ve mat logic dieu nay KHONG tu gay ra loi "chuyen man hinh" (khong co gi
 * kich no doc lai), nhung no VI PHAM mot yeu cau khac: thay doi be rong
 * khung nhin qua lai qua nguong 640px (thu nho/phong to cua so, xoay man
 * hinh) phai BAT/TAT video NGAY, hai chieu — sua bang `matchMedia(...).
 * addEventListener("change", ...)` thay vi chi doc mot lan.
 */

import { useEffect, useRef, useState } from "react";

export interface LiveBackgroundSource {
  webm?: string;
  mp4?: string;
}

export function LiveBackground({
  poster,
  video,
  mobileVideo = false,
  videoMask,
  className,
}: {
  /** Anh tinh — LUON hien, khong phu thuoc video co tai duoc hay khong. */
  poster: string;
  /**
   * Nguon video, hai dinh dang. Bo trong (`undefined`) nghia la CHUA co tai
   * san — component chi ve poster, hoan toan giong nen tinh hom nay.
   */
  video?: LiveBackgroundSource;
  /**
   * Phan 20 dac ta: mac dinh KHONG phat video o man hinh <=640px — nen di
   * dong danh cho poster tinh tru khi da co ban ma/kiem tra bang thong
   * rieng cho di dong va CHU DONG bat co nay len.
   */
  mobileVideo?: boolean;
  /**
   * V2 hybrid cinemagraph: duong dan mot anh mask (trang = hien video, den =
   * chi thay anh tinh ben duoi). Bo trong = video phu toan khung nhu V1.
   */
  videoMask?: string;
  className?: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [sanSang, setSanSang] = useState(false);
  const [loi, setLoi] = useState(false);
  const [choPhep, setChoPhep] = useState(false);
  /** Da thu tai lai sau loi hay chua — gioi han DUNG MOT LAN, xem chu thich
   * V3 o dau tep. Reset moi khi `choPhep` tat roi bat lai (video se duoc
   * mount lai tu dau, xung dang co mot co hoi thu-lai moi). */
  const daThuLaiRef = useRef(false);

  const coNguon = Boolean(video && (video.webm || video.mp4));

  // ĐỦ ĐIỀU KIỆN — REACTIVE ca hai chieu (khong chi doc mot lan luc mount).
  useEffect(() => {
    if (!coNguon || typeof window === "undefined") return;
    const qGiamChuyenDong = window.matchMedia("(prefers-reduced-motion: reduce)");
    // CHI dung `max-width` cua CSS viewport — KHONG BAO GIO doc
    // `devicePixelRatio`/`screen.width`/`screen.height`: hai gia tri do doi
    // khi keo cua so qua man hinh khac ty le DPI, va KHONG lien quan gi toi
    // "man hinh be" theo dung nghia dac ta (xem chu thich V3 o dau tep).
    const qManHinhNho = window.matchMedia("(max-width: 640px)");

    /*
      `queueMicrotask`: goi `setChoPhep` THANG trong than effect la mot
      setState DONG BO ma quy tac `react-hooks/set-state-in-effect` cam (gay
      render lien tang) — cung ly do/cung cach sua nhu `NavIndicator.tsx`.
      Gia tri MAC DINH `choPhep=false` (an toan cho SSR: server khong co
      `window`) roi nang cap NGAY sau khi gan (mot vi tac vu, khong doi mot
      chu ky ve nao ca).
    */
    const tinhLai = () => {
      /*
        `navigator.connection` la mot API khong chuan (khong co tren Safari)
        — doc qua ep kieu + optional chaining, MAC DINH cho phep khi trinh
        duyet khong biet gi ve no (khong the tu choi mot thu khong do luong
        duoc).
      */
      const conn = (navigator as unknown as { connection?: { saveData?: boolean } })
        .connection;
      const tietKiemDuLieu = conn?.saveData === true;
      setChoPhep((truoc) => {
        const moi = !qGiamChuyenDong.matches && !tietKiemDuLieu
          && (!qManHinhNho.matches || mobileVideo);
        if (truoc && !moi) {
          // Chuyen tu DU sang KHONG du dieu kien — don sach de lan sau du
          // dieu kien tro lai la mot khoi dau moi tinh (video se duoc mount
          // lai tu <video> rong, khong phai mot the cu voi `sanSang=true`
          // "thua ke" tu lan truoc gay chop den luc moi mount).
          setSanSang(false);
          setLoi(false);
          daThuLaiRef.current = false;
        }
        return moi;
      });
    };
    queueMicrotask(tinhLai);
    qGiamChuyenDong.addEventListener("change", tinhLai);
    qManHinhNho.addEventListener("change", tinhLai);
    return () => {
      qGiamChuyenDong.removeEventListener("change", tinhLai);
      qManHinhNho.removeEventListener("change", tinhLai);
    };
  }, [coNguon, mobileVideo]);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || !choPhep) return;
    /*
      Tab an thi dung phat — khong co ly do gi de giu mot video chay ngam
      khong ai nhin thay; tab hien lai thi phat tiep NEU da san sang va
      khong loi. CHI TAM DUNG/PHAT TIEP — khong dung `choPhep`/`loi` o day,
      dung nguyen tach bach "du dieu kien" vs "trang thai phat" (V3).
    */
    const onDoiHien = () => {
      if (document.hidden) el.pause();
      else if (sanSang && !loi) el.play().catch(() => {});
    };
    document.addEventListener("visibilitychange", onDoiHien);
    /*
      `pageshow`: mot so trinh duyet phuc hoi trang tu bfcache (vd sau khi
      bam Back) ma KHONG phat lai `visibilitychange` — bat them phong hờ de
      video khong o lai trang thai tam dung mai sau khi trang hien lai.
    */
    window.addEventListener("pageshow", onDoiHien);
    return () => {
      document.removeEventListener("visibilitychange", onDoiHien);
      window.removeEventListener("pageshow", onDoiHien);
    };
  }, [choPhep, sanSang, loi]);

  const hienVideo = choPhep && coNguon && !loi;

  /*
    LOI — thu TAI LAI dung MOT LAN truoc khi ket luan hong vinh vien (V3, xem
    chu thich dau tep). `el.load()` yeu cau trinh duyet nap lai tu chinh cac
    <source> hien co — neu loi la GPU context loss thoang qua (doi man hinh),
    lan tai lai nay thanh cong va video tiep tuc; neu loi that su (URL sai,
    tep hong), no se loi LAN HAI ngay sau do va roi ve poster vinh vien nhu
    truoc.
  */
  const xuLyLoiVideo = () => {
    const el = videoRef.current;
    if (el && !daThuLaiRef.current) {
      daThuLaiRef.current = true;
      el.load();
      el.play().catch(() => {});
      return;
    }
    setLoi(true);
  };

  return (
    <div className={className} style={{ position: "relative", overflow: "hidden" }}>
      {/* eslint-disable-next-line @next/next/no-img-element -- nen trang tri toan man hinh, khong phai anh noi dung; NovelCover/StoryCoverFallback trong repo cung dung mau tuong tu. */}
      <img
        src={poster}
        alt=""
        aria-hidden="true"
        className="live-bg-poster"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
      />
      {hienVideo ? (
        <video
          ref={videoRef}
          className="live-bg-video"
          aria-hidden="true"
          autoPlay
          muted
          loop
          playsInline
          preload="none"
          onCanPlay={() => setSanSang(true)}
          onError={xuLyLoiVideo}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            opacity: sanSang ? 1 : 0,
            transition: "opacity 600ms ease",
            pointerEvents: "none",
            ...(videoMask
              ? {
                  WebkitMaskImage: `url(${videoMask})`,
                  maskImage: `url(${videoMask})`,
                  WebkitMaskSize: "cover",
                  maskSize: "cover",
                  WebkitMaskRepeat: "no-repeat",
                  maskRepeat: "no-repeat",
                  // KHONG dat mac dinh o day — mask phai dung CHUNG diem neo
                  // (`object-position`) voi video, va tung trang tu dat qua
                  // CSS (xem `.home-live-lop` o globals.css) vi inline style
                  // luon thang CSS ben ngoai, khong the ghi de tu do.
                }
              : {}),
          }}
        >
          {video?.webm ? <source src={video.webm} type="video/webm" /> : null}
          {video?.mp4 ? <source src={video.mp4} type="video/mp4" /> : null}
        </video>
      ) : null}
    </div>
  );
}
