"use client";

/**
 * Lop tranh nen theo tung trang.
 *
 * V1 "Cloud Veil Route Transition": chuyen canh khi doi route KHONG con la
 * viec cua component nay nua — no chuyen sang `RouteTransitionVeil.tsx`
 * (man may/suong troi qua nen) + `lib/routeTransitionStore.ts` (dong ho
 * dieu phoi pha phu/doi anh/lo, dung chung giua hai component).
 *
 * V3 (Celestial Mist Ribbon): THEM crossfade anh nen A->B (`--dur-bg-
 * crossfade`, ~200ms). Ly do: V2 doi anh bang `key={ten}` — mot cu REMOUNT
 * cung, an duoc vi may V2 qua day dac che kin man hinh dung luc do. May V3
 * mong hon nhieu (chi con 35-60% dien tich, luon con khe ho) nen cu nhay do
 * se LO RA neu khong tan sac that. Co che: khi `ten` doi, GIU lop CU mot
 * chut (opacity 1->0) trong khi lop MOI hien vao (opacity 0->1) — CHI
 * `.page-bg-lop` (anh+vignette) tan sac, KHONG phai ca `.page-bg` hay bat ky
 * gi thuoc giao dien (dac ta cam "fade the whole page"). `.hat`/
 * `<AmbientScene>` van doi cung (chi la trang tri phu, khong can tan sac).
 *
 * Lich su (V0, truoc bao cao Cloud Veil): tung la mot co che HAI LOP tu quan
 * ly rieng (nap truoc anh, dem gio, quay may ngang theo huong tren truc) —
 * xem lich su git neu can doi chieu. Viec nap-truoc-anh khong mat di, no
 * chuyen vao `routeTransitionStore.ts` (`napAnh`), noi no co the dong bo voi
 * dong ho man suong thay vi tu chay rieng.
 *
 * KHONG dung lam bia truyen — do la viec cua `StoryCoverFallback`.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
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

  /*
    V3 crossfade: co the co HAI `.page-bg-lop` cung luc (`khoa` la so dem
    rieng — KHONG phai `ten` — de tranh trung khoa khi ten CU va ten MOI
    khac nhau nhung ta van can render CA HAI dong thoi). `fade`:

      "steady"  binh thuong (opacity 1, co transition) — trang thai on dinh
      "enter"   moi mount cho lan doi KHONG PHAI lan dau (opacity 0, KHONG
                transition — tranh mot buoc nhay hoat hinh tai chinh khung
                hinh mount), duoc chuyen sang "steady" o frame ke tiep de
                trinh duyet THAT SU noi suy 0->1
      "exit"    lop CU dang tan (opacity 1->0), tu go khoi mang khi
                `transitionend` ban (`onTransitionEnd`)

    CHI `.page-bg-lop` (anh + vignette) tan sac — `.hat`/`<AmbientScene>` ben
    duoi doc `ten` truc tiep, doi CUNG (dac ta cam "fade the whole page";
    day chi la hai chi tiet trang tri phu, khong can tan sac rieng).
  */
  const [cacLop, setCacLop] = useState<
    { ten: string; khoa: number; fade: "steady" | "enter" | "exit" }[]
  >([]);
  const khoaKeTiep = useRef(0);
  const tenTruocLop = useRef<string | null>(null);

  useEffect(() => {
    if (!ten || ten === tenTruocLop.current) return;
    const laLanDau = tenTruocLop.current === null;
    tenTruocLop.current = ten;
    const khoa = khoaKeTiep.current++;
    setCacLop((cu) => [
      ...cu.map((l) => ({ ...l, fade: "exit" as const })),
      { ten, khoa, fade: laLanDau ? "steady" : "enter" },
    ]);
    if (laLanDau) return;
    // Doi mot khung hinh de trinh duyet ghi nhan trang thai "enter" (opacity
    // 0, khong transition) TRUOC KHI doi sang "steady" — neu doi ca hai
    // cung mot lan cap nhat, React gop lai thanh MOT lan render duy nhat va
    // trinh duyet khong co gi de noi suy tu (khong thay hoat hinh).
    const id = requestAnimationFrame(() => {
      setCacLop((cu) => cu.map((l) => (l.khoa === khoa ? { ...l, fade: "steady" } : l)));
    });
    return () => cancelAnimationFrame(id);
  }, [ten]);

  function xoaLop(khoa: number) {
    setCacLop((cu) => cu.filter((l) => l.khoa !== khoa));
  }

  if (!ten) return null;

  return (
    <div className="page-bg" aria-hidden="true">
      {cacLop.map((lop) => (
        <div
          className="page-bg-lop"
          data-bg={lop.ten}
          data-fade={lop.fade}
          key={lop.khoa}
          onTransitionEnd={lop.fade === "exit" ? () => xoaLop(lop.khoa) : undefined}
        >
          {lop.ten === "home" ? (
            <LiveBackground
              poster={anhNen(lop.ten)}
              video={HOME_LIVE_BAT ? HOME_VIDEO : undefined}
              className="home-live-lop"
            />
          ) : null}
        </div>
      ))}

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
