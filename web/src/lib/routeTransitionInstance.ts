/**
 * Ban dung THAT trong trinh duyet cua `taoRouteTransitionStore` — noi DUY
 * NHAT lap ghep may che chuyen canh voi cac API trinh duyet that (Image,
 * setTimeout, matchMedia). Logic thuan (co the kiem thu voi phu thuoc gia)
 * nam o `routeTransitionStore.ts`; tep nay CHI noi day.
 *
 * MOT instance singleton — ca `PageBackground.tsx` lan `RouteTransitionVeil.
 * tsx` import CUNG mot bien nay va theo doi qua `useSyncExternalStore`, nen
 * hai component luon thay CHINH XAC mot trang thai, khong bao gio lech nhau.
 */

import { MAN_HINH_NHO, anhNen, anhNenNho, tenNen } from "@/lib/backgrounds";
import { taoRouteTransitionStore } from "@/lib/routeTransitionStore";

function napAnhThat(ten: string): Promise<void> {
  return new Promise((giai) => {
    const img = new Image();
    // Nap truoc DUNG tam se ve: dien thoai ve ban nho (CSS `--anh-nho` + poster
    // `<picture>`), nap tam lon o do la tai thua ~300 KB ma van phai tai tam nho.
    img.src = window.matchMedia(MAN_HINH_NHO).matches ? anhNenNho(ten) : anhNen(ten);
    const xong = () => giai();
    // `decode()` cho ca truong hop anh da nam trong cache: no tra ve ngay,
    // nen chuyen canh bat dau lien ma khong phai cho mot vong mang nao.
    if (img.decode) img.decode().then(xong, xong);
    else {
      img.onload = xong;
      img.onerror = xong;
    }
  });
}

export const routeTransitionStore = taoRouteTransitionStore({
  layTen: tenNen,
  dangGiamChuyenDong: () =>
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  napAnh: napAnhThat,
  datHen: (fn, ms) => window.setTimeout(fn, ms) as unknown as number,
  huyHen: (id) => window.clearTimeout(id),
});
