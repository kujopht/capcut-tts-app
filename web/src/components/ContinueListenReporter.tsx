"use client";

/**
 * Ghi con trỏ "Tiếp tục nghe" (Phần B, V4 visual completion) — vị trí GIÂY
 * hiện tại, không phải số giây đã nghe được như `ListenReporter`.
 *
 * TÁCH RIÊNG khỏi `ListenReporter` có chủ ý, cùng lý do component đó tách
 * khỏi `AudioEngine`: hai khái niệm khác nhau — `ListenReporter` đếm để tính
 * UY TÍN công khai của tác giả (đếm giây thật đã chạy, không đọc con trỏ),
 * còn component này ghi VỊ TRÍ để người nghe tự quay lại đúng chỗ, không ảnh
 * hưởng uy tín ai. Gộp chung sẽ buộc một thay đổi ở nhu cầu này rò sang nhu
 * cầu kia.
 *
 * Nhịp 15 giây khi đang phát — đủ gần để tua lại không mất nhiều, đủ thưa để
 * không làm nghẽn mạng trên một chương dài hàng giờ.
 */

import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { useAudioEngine } from "@/components/AudioEngine";

const NHIP_GIAY = 15;

export function ContinueListenReporter({
  novelId,
  chapterId,
}: {
  novelId: string;
  chapterId: string;
}) {
  const { trangThai } = useAudioEngine();
  const viTriDaGui = useRef(-1);
  /*
    `thoiDiem` PHAI doc qua ref, khong phai truc tiep trong closure cua
    `setInterval`. Neu them `trangThai.thoiDiem` vao mang phu thuoc, effect
    se HUY VA TAO LAI bo dem moi giay (no doi lien tuc trong luc phat) — mat
    het tac dung "moi 15 giay". Neu KHONG them nhung van doc truc tiep tu
    `trangThai` (loi ban dau o day), closure giu mai gia tri LUC EFFECT CHAY,
    va vi tri bao len se dung yen mai o giay dau tien.
  */
  const thoiDiemRef = useRef(0);
  useEffect(() => {
    thoiDiemRef.current = trangThai.thoiDiem;
  }, [trangThai.thoiDiem]);

  useEffect(() => {
    if (!trangThai.dangPhat) return;
    const nhip = window.setInterval(() => {
      const viTri = Math.floor(thoiDiemRef.current);
      if (viTri <= 0 || viTri === viTriDaGui.current) return;
      viTriDaGui.current = viTri;
      void api.reportListenProgress(novelId, chapterId, viTri).catch((cause) => {
        // KHONG lam gian doan viec nghe va KHONG hien gi cho nguoi dung — cung
        // ly do voi `ListenReporter`: day la tien ich hau truong, mot lan mat
        // mang khong duoc bien thanh thong bao loi giua chung.
        //
        // Nhung KHONG nuot am tham: log ra console de con thay duoc khi debug
        // (vd server tra 422 vi validation sai — nhu bug tran 24h da tung xay
        // ra voi `position_seconds`). Chi console.error, khong alert/toast.
        console.error("reportListenProgress that bai:", cause);
      });
    }, NHIP_GIAY * 1000);
    return () => window.clearInterval(nhip);
  }, [trangThai.dangPhat, novelId, chapterId]);

  return null;
}
