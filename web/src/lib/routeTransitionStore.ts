/**
 * Kho trang thai DUNG CHUNG cho chuyen canh route — "Cloud Veil Route
 * Transition V1". Thay THE HOAN TOAN cho co che quay-may-ngang cu (xem lich
 * su git `components/PageBackground.tsx` truoc bao cao nay).
 *
 * VI SAO MOT KHO RIENG, KHONG DAT TRONG COMPONENT: hai component can CUNG
 * MOT trang thai TAI CUNG MOT THOI DIEM —
 *
 *   `PageBackground.tsx`      quyet dinh HINH ANH nao dang hien (`ten`)
 *   `RouteTransitionVeil.tsx` quyet dinh MAY CHE dang o pha nao (`trangThai`)
 *
 * — va chung PHAI dong bo tuyet doi (anh doi DUNG luc man suong che kin),
 * nen khong the la hai state rieng trong hai component doan-thoi-diem-cua-
 * nhau bang setTimeout doc lap (de lech, de dua). MOT kho, hai component
 * cung theo doi qua `useSyncExternalStore`.
 *
 * KIEM THU DUOC MA KHONG CAN JSDOM: `taoRouteTransitionStore` nhan moi phu
 * thuoc cham toi trinh duyet (nap anh, hen gio, giam chuyen dong) qua tham
 * so — bo test dung `node:test` co the tiem cac ham gia, dieu khien "gio"
 * bang tay, va kiem tra CHINH XAC may co chay dung trinh tu, dung nguyen tac
 * chong-dua (race) khi dieu huong lien tiep hay khong. Day la phan RUI RO
 * NHAT cua tinh nang nay — dang duoc kiem that, khong chi quet chu trong ma
 * nguon.
 */

export type TrangThaiVeil = "idle" | "covering" | "revealing";

export interface RouteTransitionSnapshot {
  duongDan: string;
  /**
   * Chu de nen dang duoc VE THAT (`PageBackground.tsx` dung gia tri nay).
   * Van la chu de CU trong suot pha "covering" — chi doi thanh dich luc doi
   * anh THAT SU xay ra (giua luc man suong che kin). `null` truoc lan phan
   * giai dau tien.
   */
  ten: string | null;
  /**
   * Chu de DICH cua lan chuyen canh dang chay — dung de MAN SUONG chon mau
   * (`RouteTransitionVeil.tsx`) tu luc bat dau che, TRUOC CA khi `ten` kip
   * doi. `null` khi khong co chuyen canh nao dang chay (luc do man suong
   * dung `ten` — xem `RouteTransitionVeil.tsx`).
   */
  tenDich: string | null;
  trangThai: TrangThaiVeil;
}

export interface Timing {
  /** Do dai pha "may quet toi" (ms) — cung la MOC toi thieu truoc khi doi anh. */
  PHU: number;
  /** Do dai pha "may quet tiep + tan dan" (ms). */
  LO: number;
}

/**
 * KHOP CHINH XAC voi `--dur-veil-phu`/`--dur-veil-lo` o `globals.css` — hai
 * cho phai noi CUNG mot con so, xem `route-transition-veil.test.mjs`.
 *
 * V2: 340 + 50 (dem) + 490 = 880ms tong — trong khoang 780-900ms dac ta
 * (V1 la 650ms, bi nhan xet "van con doc hoi giong mot cu lau" — V2 keo dai
 * VA lam muot hon, nhung KHONG lam cham diem doi anh: `PHU` (340ms) van la
 * moc anh doi, chi rieng qua trinh may quet TIEP TUC sau do (`LO`, 490ms)
 * dai hon de tao cam giac mot duong quet lien tuc thay vi "phinh-xep".
 */
export const THOI_LUONG_BINH_THUONG: Timing = { PHU: 340, LO: 490 };
/** `prefers-reduced-motion: reduce` — gan nhu tuc thi, nhung KHONG bao gio 0:
 * doi nen giua hai mau khac nhau van can mot lan che, neu khong se thay mot
 * cai nhay mau song. */
export const THOI_LUONG_GIAM: Timing = { PHU: 90, LO: 60 };

/**
 * Tran an toan cho viec cho anh nap — mot ket noi mang bi treo (khong bao gio
 * bao `load` lan `error`) se KHONG con lam man suong ket dinh mai. Rat hiem
 * gap trong thuc te (`napAnhThat` da tu giai quyet qua `onerror`), day chi la
 * lop phong ve thu hai.
 */
const TRAN_CHO_ANH_MS = 2000;

export interface RouteTransitionDeps {
  /** `tenNen` — suy chu de nen tu duong dan. */
  layTen: (duongDan: string) => string;
  /** `true` khi nguoi dung chon `prefers-reduced-motion: reduce`. */
  dangGiamChuyenDong: () => boolean;
  /** Nap truoc anh cua mot chu de; PHAI luon resolve (ke ca khi loi). */
  napAnh: (ten: string) => Promise<void>;
  datHen: (fn: () => void, ms: number) => number;
  huyHen: (id: number) => void;
}

export function taoRouteTransitionStore(deps: RouteTransitionDeps) {
  let state: RouteTransitionSnapshot = {
    duongDan: "",
    ten: null,
    tenDich: null,
    trangThai: "idle",
  };
  const nguoiNghe = new Set<() => void>();
  const henDangCho: number[] = [];
  /**
   * The he cua lan dieu huong DANG XU LY. Moi lan `diTinh` goi voi mot chu de
   * KHAC chu de hien tai se tang bien nay len — bat ky continuation nao (promise
   * .then) tu mot the he CU hon deu tu kiem tra va bo qua chinh no. Day la
   * toan bo co che chong dua (race) khi nguoi dung dieu huong lien tiep truoc
   * khi lan truoc ket thuc: KHONG can huy promise (khong the), chi can lam
   * ket qua cua no VO NGHIA.
   */
  let theHe = 0;

  function set(phanMoi: Partial<RouteTransitionSnapshot>) {
    state = { ...state, ...phanMoi };
    nguoiNghe.forEach((fn) => fn());
  }

  function huyHenDangCho() {
    while (henDangCho.length) {
      const id = henDangCho.pop();
      if (id !== undefined) deps.huyHen(id);
    }
  }

  /** Xoa MOT hen khoi so sach ma KHONG dung toi (id da tu chay xong, hoac
   * chu dong huy rieng no — xem `choCoTheHuy`). */
  function boKhoiSoSach(id: number) {
    const i = henDangCho.indexOf(id);
    if (i !== -1) henDangCho.splice(i, 1);
  }

  function hen(fn: () => void, ms: number) {
    const id = deps.datHen(() => {
      boKhoiSoSach(id);
      fn();
    }, ms);
    henDangCho.push(id);
    return id;
  }

  function cho(ms: number): Promise<void> {
    return new Promise((giai) => hen(() => giai(), ms));
  }

  /**
   * Nhu `cho`, nhung tra them mot ham HUY RIENG — dung cho `TRAN_CHO_ANH_MS`:
   * day la mot hen "phong hờ" chay DUA (race) voi viec nap anh, va o duong
   * day nhanh (anh nap xong truoc) hen nay se KHONG BAO GIO tu chay — neu
   * khong chu dong huy, no nam lai trong hang doi that cua trinh duyet (hoac
   * cua dong ho gia trong bai test) den 2 giay sau MOI lan chuyen canh, dung
   * nguyen dieu "chi phi luc dung yen phai la khong" ma dac ta cam.
   */
  function choCoTheHuy(ms: number): [Promise<void>, () => void] {
    let id = -1;
    const p = new Promise<void>((giai) => {
      id = hen(() => giai(), ms);
    });
    return [p, () => {
      boKhoiSoSach(id);
      deps.huyHen(id);
    }];
  }

  /**
   * Diem vao DUY NHAT — goi moi lan phat hien `duongDan` doi (xem
   * `PageBackground.tsx`). Tra ve khong dong bo; trang thai cap nhat qua
   * `subscribe`.
   */
  function diTinh(duongDanMoi: string) {
    const tenMoi = deps.layTen(duongDanMoi);

    // Lan dau: chua co gi de chuyen canh TU — hien thang, khong may che.
    if (state.ten === null) {
      huyHenDangCho();
      theHe += 1;
      set({ duongDan: duongDanMoi, ten: tenMoi, tenDich: null, trangThai: "idle" });
      return;
    }

    // Cung mot chu de (vd `/fanfic` -> `/novels/x`, hoac dieu huong nham quay
    // ve dung chu de dang hien giua luc mot lan chuyen canh khac con dang
    // chay): KHONG can may che. Neu dang co mot lan chuyen canh giua chung,
    // huy sach — day la nhanh "resolve deterministically" khi tenMoi trung
    // dung chu de dang (hoac se) hien.
    if (tenMoi === state.ten) {
      huyHenDangCho();
      theHe += 1;
      set({ duongDan: duongDanMoi, trangThai: "idle", tenDich: null });
      return;
    }

    // Khac chu de: (khoi dong lai) mot chu ky phu -> doi anh -> lo. Neu dang
    // co mot lan chuyen canh khac dang chay, no bi THAY THE hoan toan o day —
    // khong xep hang, khong chay song song hai hoat hinh.
    huyHenDangCho();
    theHe += 1;
    const heNay = theHe;
    const T = deps.dangGiamChuyenDong() ? THOI_LUONG_GIAM : THOI_LUONG_BINH_THUONG;

    set({ duongDan: duongDanMoi, trangThai: "covering", tenDich: tenMoi });

    const [tranAnToan, huyTranAnToan] = choCoTheHuy(TRAN_CHO_ANH_MS);
    // Huy hen "phong hờ" NGAY khi cuoc dua ket thuc (du ben nao thang) — o
    // duong day nhanh (nap anh xong truoc), khong de mot hen 2 giay nam lai
    // vo ich trong hang doi that cua trinh duyet.
    const sanSang = Promise.race([deps.napAnh(tenMoi), tranAnToan]).then(huyTranAnToan);
    // Moc PHU la thoi gian TOI THIEU truoc khi doi anh — de pha "may che dan"
    // luon co du thoi gian hien het tren man hinh truoc khi noi dung phia sau
    // no doi, ke ca khi anh da nam san trong cache.
    const choToiThieu = cho(T.PHU);

    Promise.all([sanSang, choToiThieu]).then(() => {
      if (heNay !== theHe) return; // co lan dieu huong khac da thay the

      set({ ten: tenMoi, tenDich: null }); // doi NGAY — luc nay man suong dang che kin

      // Dem them mot khoang dem NHO truoc khi lo — dam bao man suong da THAT
      // SU che kin (khong chi vua doi xong) truoc khi bat dau rut di. Voi
      // duong day nhanh (anh nam san trong cache), khoang nay + T.PHU vua
      // khop luc hoat hinh "phu" tu nhien ket thuc (`--dur-veil-phu`), nen
      // khong co mot buoc nhay nao giua hai pha.
      hen(() => {
        if (heNay !== theHe) return;
        set({ trangThai: "revealing" });
        hen(() => {
          if (heNay !== theHe) return;
          set({ trangThai: "idle" });
        }, T.LO);
      }, 50);
    });
  }

  return {
    getSnapshot: (): RouteTransitionSnapshot => state,
    subscribe(fn: () => void): () => void {
      nguoiNghe.add(fn);
      return () => {
        nguoiNghe.delete(fn);
      };
    },
    diTinh,
  };
}

export type RouteTransitionStore = ReturnType<typeof taoRouteTransitionStore>;
