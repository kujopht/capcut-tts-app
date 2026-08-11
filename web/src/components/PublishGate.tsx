"use client";

/**
 * CONG CHAN XUAT BAN.
 *
 * Nguyen tac: ai cung viet duoc, chi khong ai cung dua ra cong khai duoc. Tao
 * truyen, sua truyen, them chuong, tao audio, xoa ban nhap — khong mot thao tac
 * nao trong so do di qua day. Chi NUT XUAT BAN.
 *
 * Va khi cong dong, no KHONG hien mot loi. Cho do la mot khoanh khac nguoi ta
 * vua viet xong mot chuong va dang muon dua no ra; thu ho can khong phai mot
 * thong bao tu choi ma la buoc tiep theo. Nen moi trang thai dan toi mot hanh
 * dong khac nhau:
 *
 *   none       -> "Dang ky tac gia"        (mo `/creator/apply`)
 *   pending    -> "Dang cho duyet"         (mo, giai thich, ban nhap van sua duoc)
 *   rejected   -> "Gui lai don"            (mo `/creator/apply`)
 *   suspended  -> khoa, va noi ro truyen cu VAN cong khai
 *   approved   -> nut xuat ban binh thuong
 *
 * MAY CHU van la noi quyet dinh. Component nay chi lo hinh dang cua buoc tiep
 * theo; `POST /api/novels/{id}/publish` co phep kiem cua rieng no, va mot client
 * bi sua van khong xuat ban duoc.
 */

import Link from "next/link";
import { useCallback } from "react";
import { api, type CreatorState } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";

/**
 * Nap trang thai tac gia MOT lan cho ca trang.
 *
 * `null` = chua biet (dang tai, hoac goi that bai). Luc do nut xuat ban van hien
 * binh thuong: neu may chu tu choi thi nguoi dung nhan dung thong diep tu may
 * chu — an nut vi mot loi mang la chan nguoi dung vi mot viec khong phai loi ho.
 *
 * Dung `useAsyncData` chu khong tu viet `useEffect` + `setState`: quy tac
 * `react-hooks/set-state-in-effect` cam goi `setState` DONG BO trong than
 * effect, va hook do la cho du an nay da giai quyet dieu do mot lan.
 */
export function useTrangThaiCreator(daDangNhap: boolean) {
  const nap = useCallback(
    () => (daDangNhap ? api.creatorMe() : Promise.resolve(null)),
    [daDangNhap],
  );
  const { data, reload } = useAsyncData<CreatorState | null>(nap);
  return { trangThai: data ?? null, napLai: reload };
}

export function CongXuatBan({
  trangThai,
  coTheXuatBan,
  onXuatBan,
}: {
  trangThai: CreatorState | null;
  /** Dieu kien cua chinh truyen — vd phai co it nhat mot chuong. */
  coTheXuatBan: boolean;
  onXuatBan: () => void;
}) {
  // Chua biet trang thai: cu hien nut. Xem `useTrangThaiCreator`.
  const status = trangThai?.author_status;
  const duoc = !trangThai || trangThai.can_publish;

  if (duoc) {
    return (
      <button
        type="button"
        className="btn btn-primary btn-sm"
        onClick={onXuatBan}
        disabled={!coTheXuatBan}
      >
        Xuất bản
      </button>
    );
  }

  if (status === "pending") {
    return (
      <span className="cong-xb">
        <span className="badge">Đang chờ duyệt</span>
        <span className="hint">Bản nháp vẫn sửa được.</span>
      </span>
    );
  }

  if (status === "suspended") {
    return (
      <span className="cong-xb">
        <span className="badge badge-warn">Tạm dừng xuất bản</span>
        <span className="hint">Truyện đã xuất bản vẫn công khai.</span>
      </span>
    );
  }

  return (
    <Link
      className="btn btn-primary btn-sm"
      href="/creator/apply?next=/write"
    >
      {status === "rejected" ? "Gửi lại đơn tác giả" : "Đăng ký tác giả"}
    </Link>
  );
}
