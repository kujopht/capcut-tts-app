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
 * CHUA DUOC GAN VAO TRANG NAO — day la ly do: dem nay KHONG co tai san
 * video nao duoc sinh ra (xem bao cao overnight — nghen o buoc sinh video vi
 * khong co provider kha dung trong phien nay). Component o day la kien truc
 * SAN SANG, da kiem thu day du, cho lan tich hop dau tien khi co video that.
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
  className?: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [sanSang, setSanSang] = useState(false);
  const [loi, setLoi] = useState(false);
  const [choPhep, setChoPhep] = useState(false);

  const coNguon = Boolean(video && (video.webm || video.mp4));

  useEffect(() => {
    if (!coNguon || typeof window === "undefined") return;
    /*
      `queueMicrotask`: goi `setChoPhep` THANG trong than effect la mot
      setState DONG BO ma quy tac `react-hooks/set-state-in-effect` cam (gay
      render lien tang) — cung ly do/cung cach sua nhu `NavIndicator.tsx`.
      Gia tri MAC DINH `choPhep=false` (an toan cho SSR: server khong co
      `window`) roi nang cap NGAY sau khi gan (mot vi tac vu, khong doi mot
      chu ky ve nao ca).
    */
    queueMicrotask(() => {
      const giamChuyenDong = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      /*
        `navigator.connection` la mot API khong chuan (khong co tren Safari)
        — doc qua ep kieu + optional chaining, MAC DINH cho phep khi trinh
        duyet khong biet gi ve no (khong the tu choi mot thu khong do luong
        duoc).
      */
      const conn = (navigator as unknown as { connection?: { saveData?: boolean } })
        .connection;
      const tietKiemDuLieu = conn?.saveData === true;
      const laManHinhNho = window.matchMedia("(max-width: 640px)").matches;
      setChoPhep(!giamChuyenDong && !tietKiemDuLieu && (!laManHinhNho || mobileVideo));
    });
  }, [coNguon, mobileVideo]);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || !choPhep) return;
    /*
      Tab an thi dung phat — khong co ly do gi de giu mot video chay ngam
      khong ai nhin thay; tab hien lai thi phat tiep NEU da san sang va
      khong loi.
    */
    const onDoiHien = () => {
      if (document.hidden) el.pause();
      else if (sanSang && !loi) el.play().catch(() => {});
    };
    document.addEventListener("visibilitychange", onDoiHien);
    return () => document.removeEventListener("visibilitychange", onDoiHien);
  }, [choPhep, sanSang, loi]);

  const hienVideo = choPhep && coNguon && !loi;

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
          onError={() => setLoi(true)}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            opacity: sanSang ? 1 : 0,
            transition: "opacity 600ms ease",
            pointerEvents: "none",
          }}
        >
          {video?.webm ? <source src={video.webm} type="video/webm" /> : null}
          {video?.mp4 ? <source src={video.mp4} type="video/mp4" /> : null}
        </video>
      ) : null}
    </div>
  );
}
