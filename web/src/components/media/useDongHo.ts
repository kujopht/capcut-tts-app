"use client";

/**
 * DONG HO PHAT LAI dung chung cho ca trinh soan.
 *
 * §12 doi mot dieu: "Timeline and preview use the same playback clock."
 * Cach sai — va cach de roi vao nhat — la de `<video>` tu chay roi doc
 * `currentTime` o mot cho, con duong thoi gian tu dem bang `setInterval` o
 * cho khac. Hai nguon thoi gian se TROI khoi nhau; voi mot doan vai phut,
 * do troi du de phu de hien lech han mot cau.
 *
 * O day chi co MOT so: `giay`. Khi co video thi video la NGUON CHUAN va ta
 * doc nguoc tu no; khong co video (che do chi-audio) thi ta tu dem bang
 * `performance.now()`. Doi giua hai che do khong lam mat vi tri dang phat.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface DongHo {
  giay: number;
  dangPhat: boolean;
  phat: () => void;
  dung: () => void;
  batTat: () => void;
  /** Nhay toi mot giay. Dung ca khi dang phat lan khi dang dung. */
  nhay: (giay: number) => void;
  /** Gan `<video>` lam nguon chuan. `null` = tro lai dong ho tu dem. */
  datVideo: (el: HTMLVideoElement | null) => void;
}

export function useDongHo(tongDai: number): DongHo {
  const [giay, datGiay] = useState(0);
  const [dangPhat, datDangPhat] = useState(false);

  const video = useRef<HTMLVideoElement | null>(null);
  const rAF = useRef(0);
  // Moc cua dong ho TU DEM: thoi diem `performance.now()` ung voi `giay = 0`.
  const moc = useRef(0);
  /*
    `giayRef` la ban sao doc duoc BEN TRONG vong rAF — `giay` cua state thi
    dong bang trong closure cua mot lan render. No duoc ghi o DUNG MOT cho
    (`ghi`), khong phai o than component: ghi ref trong lúc render la thu
    `react-hooks/refs` chan, va no chan dung — mot ref sua giua chung mot lan
    render se khien hai component doc ra hai gia tri khac nhau.
  */
  const giayRef = useRef(0);
  const daiRef = useRef(tongDai);

  // Tong dai doi khi nguoi dung keo clip. Dong bo trong effect, khong trong
  // than render.
  useEffect(() => {
    daiRef.current = tongDai;
  }, [tongDai]);

  const ghi = useCallback((g: number) => {
    const chan = Math.max(0, Math.min(daiRef.current, g));
    giayRef.current = chan;
    datGiay(chan);
    return chan;
  }, []);

  /* ------------------------------------------------------------- vong lap */

  useEffect(() => {
    if (!dangPhat) return undefined;

    const buoc = () => {
      const v = video.current;
      if (v && !v.paused && !v.ended) {
        // Video la nguon chuan khi no THAT SU dang chay. `paused` van dung
        // ngay sau `play()` chua kip khoi dong, nen ta khong doc lung tung o
        // khoanh khac do ma giu nguyen dong ho tu dem.
        ghi(v.currentTime);
      } else {
        ghi((performance.now() - moc.current) / 1000);
      }
      if (giayRef.current >= daiRef.current) {
        datDangPhat(false);
        return;
      }
      rAF.current = requestAnimationFrame(buoc);
    };

    moc.current = performance.now() - giayRef.current * 1000;
    rAF.current = requestAnimationFrame(buoc);
    return () => cancelAnimationFrame(rAF.current);
  }, [dangPhat, ghi]);

  /* ----------------------------------------------------------- dieu khien */

  const phat = useCallback(() => {
    // Phat lai tu dau khi dang dung o cuoi — neu khong, bam Play o cuoi
    // duong thoi gian se khong lam gi ca va trong nhu mot nut hong.
    if (giayRef.current >= daiRef.current - 0.05) ghi(0);
    moc.current = performance.now() - giayRef.current * 1000;
    datDangPhat(true);
  }, [ghi]);

  const dung = useCallback(() => datDangPhat(false), []);
  const batTat = useCallback(() => {
    if (dangPhat) dung();
    else phat();
  }, [dangPhat, dung, phat]);

  const nhay = useCallback(
    (g: number) => {
      const chan = ghi(g);
      moc.current = performance.now() - chan * 1000;
      const v = video.current;
      if (v) {
        try {
          v.currentTime = chan;
        } catch {
          /* video chua san sang — `onLoadedMetadata` se dat lai */
        }
      }
    },
    [ghi],
  );

  const datVideo = useCallback((el: HTMLVideoElement | null) => {
    video.current = el;
  }, []);

  return { giay, dangPhat, phat, dung, batTat, nhay, datVideo };
}
