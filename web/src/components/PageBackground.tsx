"use client";

/**
 * Lop tranh nen theo tung trang.
 *
 * MOT phan tu duy nhat, `position: fixed`, nam duoi toan bo noi dung. No khong
 * nhan chuot, khong cuon theo trang, va khong bao gio bi ve lai vi trang thai
 * React: component nay chi ve lai khi DUONG DAN doi.
 *
 * Anh dat bang CSS chu khong phai the `<img>`: mot the anh se tham gia bo cuc,
 * co the gay xo trang khi tai xong, va can them ma de giu no phia sau. Nen o
 * day chi la mot thuoc tinh `data-bg` — moi thu con lai o `globals.css`.
 *
 * CHI la khong khi. Lop phu toi 70-88% nam tren anh de chu luon la thu doc
 * duoc truoc tien; trang doc chuong toi nhat vi do la trang co yeu cau doc de
 * cao nhat.
 *
 * KHONG dung lam bia truyen. Bia rieng cho tung truyen la viec khac, lam sau.
 *
 * Bang anh xa nam o `lib/backgrounds.ts` de bo test cham toi duoc.
 */

import { usePathname } from "next/navigation";
import { tenNen } from "@/lib/backgrounds";

export function PageBackground() {
  const duong_dan = usePathname();
  return (
    <div className="page-bg" data-bg={tenNen(duong_dan)} aria-hidden="true">
      {/*
        Lop hat sang. CSS quyet dinh no co hien hay khong — chi trang chu,
        dang nhap va tai khoan moi ve, va no bien mat hoan toan khi nguoi dung
        chon giam chuyen dong. Mot phan tu, khong phai vai tram.
      */}
      <div className="hat" />
    </div>
  );
}
