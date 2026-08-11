"use client";

/**
 * Bao mot lan nghe len may chu, de tinh uy tin cho tac gia.
 *
 * TACH RIENG khoi `AudioEngine` co y: engine la thu dieu khien mot the `<audio>`
 * va khong biet gi ve tac gia hay uy tin. Nhet phep dem nay vao trong do se buoc
 * moi cho dung engine phai keo theo mot khai niem khong lien quan — va engine la
 * mot trong nhung tep KHONG duoc sua o dot nay.
 *
 * DEM THOI GIAN NGHE THAT, khong doc vi tri con tro. Doc `currentTime` thi ai
 * cung tua toi 0:31 la "nghe du 30 giay". O day mot nhip 1 giay chi cong khi
 * `dangPhat` la that, nen so giay bao len la so giay am thanh da that su chay.
 *
 * BAO MOT LAN moi lan mo trang. May chu con ap ba phep kiem nua — nguong, tu
 * nghe, va mot lan moi 24 gio — nen day chi la buoc GUI, khong phai buoc quyet
 * dinh. Component nay khong bao gio hien gi ca.
 */

import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { useAudioEngine } from "@/components/AudioEngine";

/** Khop voi `QUALIFY_SECONDS` / `QUALIFY_RATIO` o `server/creator.py`. */
const DU_LAU = 30;
const TI_LE = 0.75;

export function ListenReporter({ chapterId }: { chapterId: string }) {
  const { trangThai } = useAudioEngine();
  const daGui = useRef(false);
  const nghe = useRef(0);

  // Doi chuong thi dem lai tu dau.
  useEffect(() => {
    daGui.current = false;
    nghe.current = 0;
  }, [chapterId]);

  useEffect(() => {
    if (!trangThai.dangPhat || daGui.current) return;

    const nhip = window.setInterval(() => {
      nghe.current += 1;
      const dai = trangThai.thoiLuong;
      const can = dai > 0 ? Math.min(DU_LAU, dai * TI_LE) : DU_LAU;
      if (nghe.current < can || daGui.current) return;

      // Dat co TRUOC khi goi: mot nhip nua co the chay truoc khi request ve, va
      // hai request cho cung mot lan nghe la thua (may chu se bo cai thu hai,
      // nhung tot han la dung gui).
      daGui.current = true;
      void api.reportListen(chapterId, nghe.current).catch(() => {
        /*
          Nuot loi CO Y. Day la mot phep dem o hau truong; mot loi mang o day
          khong duoc bien thanh mot thong bao do cho nguoi dang nghe truyen.
          Mat mot luot dem la mot cai gia chap nhan duoc.
        */
      });
    }, 1000);

    return () => window.clearInterval(nhip);
  }, [trangThai.dangPhat, trangThai.thoiLuong, chapterId]);

  return null;
}
