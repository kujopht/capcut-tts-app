"use client";

/**
 * Lop tranh nen theo tung trang.
 *
 * V1 "Cloud Veil Route Transition": chuyen canh khi doi route KHONG con la
 * viec cua component nay nua — no chuyen sang `RouteTransitionVeil.tsx`
 * (man may/suong che kin man hinh) + `lib/routeTransitionStore.ts` (dong ho
 * dieu phoi pha phu/doi anh/lo, dung chung giua hai component). Component o
 * day gio CHI con MOT viec: VE dung chu de (`ten`) dang duoc kho cho phep
 * hien — vi kho da dam bao viec doi `ten` LUON xay ra dung luc man suong che
 * kin, nen o day khong can bat ky hoat hinh rieng nao (khong con "dang mo
 * ra"/"dang hien vao", khong con huong trai/phai).
 *
 * Lich su (V0, truoc bao cao Cloud Veil): tung la mot co che HAI LOP tu quan
 * ly rieng (nap truoc anh, dem gio, quay may ngang theo huong tren truc) —
 * xem lich su git neu can doi chieu. Viec nap-truoc-anh khong mat di, no
 * chuyen vao `routeTransitionStore.ts` (`napAnh`), noi no co the dong bo voi
 * dong ho man suong thay vi tu chay rieng.
 *
 * KHONG dung lam bia truyen — do la viec cua `StoryCoverFallback`.
 */

import { useEffect, useRef, useSyncExternalStore } from "react";
import { anhNen } from "@/lib/backgrounds";
import { AmbientScene } from "@/components/AmbientScene";
import { LiveBackground } from "@/components/LiveBackground";
import { routeTransitionStore } from "@/lib/routeTransitionInstance";

/**
 * Live Wallpaper — Gemini V2 (2026-08). CHI trang chu.
 *
 * Lich su: Nova Reel V1 (video toan khung, camera zoom ~5%/6s) va Nova Reel V2
 * hybrid (video da on dinh + mask cuc bo) DEU bi tu choi o QA thu cong — xem
 * lich su git. Gemini V1 (video dau tien nguoi dung tu tao) da thu o staging;
 * nguoi dung tu danh gia va cung cap Gemini V2 (chat luong cao hon) de thay
 * the — day la ban dang dung, KHONG chong len ban Gemini V1.
 *
 * Video nay do NGUOI DUNG tu tao bang Gemini (khong qua Pollinations, khong
 * ton Pollen). Kiem tra nhanh (khong OpenCV/on dinh hoa/mask — nguoi dung da
 * duyet thu cong): camera on dinh, khong bien dang lau dai/nhan vat/thuyen,
 * khong nhap nhay do sang (<1% xuyen suot 10s).
 *
 * Video toan khung, giong cau truc Gemini V1/Nova Reel V1 ban dau (poster ->
 * video crossfade, KHONG mask, KHONG on dinh hoa OpenCV).
 *
 * TUONG THICH Cloud Veil: khi ROI trang chu, `ten` doi tu "home" sang chu de
 * khac DUNG LUC man suong che kin (xem kho chuyen canh) — React go han
 * `<LiveBackground>` (dieu kien `ten === "home"` ben duoi) ngay tai thoi
 * diem do, nen video KHONG BAO GIO bi thay the/dung khi nguoi dung con thay
 * duoc no. Khi VAO trang chu cung vay: LiveBackground mount luc con bi che,
 * va tu no da ve poster truoc/video sau (xem chinh component do) — nen luc
 * man suong lo ra, nguoi dung thay poster net ngay, video chi hien sau khi
 * tai xong. Khong can them co "tam ngung" nao o day.
 */
const HOME_LIVE_BAT = true;
const HOME_VIDEO = {
  mp4: "/artwork/fantasy-backgrounds/home-live-gemini-v2.mp4",
};

export function PageBackground() {
  const { ten, duongDan } = useSyncExternalStore(
    routeTransitionStore.subscribe,
    routeTransitionStore.getSnapshot,
    // Server: chua biet duong dan nao ca — `ten === null` -> component ve
    // `null`, giong het hanh vi client truoc khi hieu ung dau tien chay.
    () => routeTransitionStore.getSnapshot(),
  );

  /*
    Doc `location.pathname` thay vi `usePathname()`.

    `usePathname()` buoc component phai o trong cay dieu huong cua Next va se
    ve lai theo moi lan route doi — dung, nhung o day ta con can BIET truoc khi
    bao kho, va Next dieu huong bang History API nen khong phat `popstate` khi
    `pushState`. Mot vong kiem nho la du, va no khong dong vao trang thai route.
  */
  const duongDanTruoc = useRef<string | null>(null);
  useEffect(() => {
    /*
      Chi goi `diTinh` khi duong dan THAT SU doi — vong kiem 120ms nay chay
      MAI MAI (suot doi trang), nen neu goi `diTinh` moi nhip du khong co gi
      doi, kho se `set()` (va lam CA HAI component ve lai) moi 120ms VO HAN,
      dung nguyen dieu "khong duoc kich hoat hoat hinh lien tuc luc dung yen"
      ma dac ta cam.
    */
    const doc = () => {
      const duong = window.location.pathname;
      if (duong === duongDanTruoc.current) return;
      duongDanTruoc.current = duong;
      routeTransitionStore.diTinh(duong);
    };
    doc();
    const id = window.setInterval(doc, 120);
    window.addEventListener("popstate", doc);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("popstate", doc);
    };
  }, []);

  if (!ten) return null;

  return (
    <div className="page-bg" aria-hidden="true">
      {/* MOT lop DUY NHAT — `key` doi theo chu de de LiveBackground (con cua
          no, chi mount o "home") gan lai sach moi lan quay ve trang chu. */}
      <div className="page-bg-lop" data-bg={ten} key={ten}>
        {ten === "home" ? (
          <LiveBackground
            poster={anhNen(ten)}
            video={HOME_LIVE_BAT ? HOME_VIDEO : undefined}
            className="home-live-lop"
          />
        ) : null}
      </div>

      {/* Hat sang — CSS quyet dinh trang nao ve. Mot phan tu, khong phai vai tram. */}
      <div className="hat" data-bg={ten} />

      {/*
        Khong khi rieng cua tung khu vuc. Dat o DAY chu khong o `layout.tsx`:
        component nay da theo doi `pathname` roi, va them mot cho nua theo doi
        cung mot thu la them mot cho nua co the lech.
      */}
      <AmbientScene duongDan={duongDan || "/"} />
    </div>
  );
}
