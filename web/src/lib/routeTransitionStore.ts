/**
 * Kho trang thai DUNG CHUNG cho chuyen canh route — "Aether Rift Reveal V4".
 *
 * LICH SU: V1-V2-V3 (man may/suong) DEU bi tu choi o khau thi giac — V3 cu
 * the bi nhan xet "doc ra nhu polygon/CSS demo, van cam giac co gi do TRUOT
 * qua man hinh, chuyen canh cam giac bi TRE (delay dau vao)". Nguyen nhan
 * KHONG chi o hinh hoc: ca ba ban truoc DEU bat dieu huong CHO mot khoang
 * toi thieu (V1 400ms, V2/V3 340ms — bien `PHU` cu) TRUOC KHI doi anh nen —
 * nghia la nguoi dung bam link, thay NavIndicator nhay ngay, nhung nen/anh
 * moi khong xuat hien cho toi khi man may "che xong". V4 BO HAN co che nay.
 *
 * MO HINH MOI: khong con "che roi doi roi lo" — thay bang MOT lop REVEAL
 * duy nhat. Nen MOI (`tenMoi`) duoc ve NGAY LAP TUC (khong cho `napAnh`,
 * khong cho mot moc toi thieu nao) o TREN nen CU (`ten`, van con nguyen o
 * duoi, chua bi doi/dich chuyen) — rieng PHAN HINH ANH nao cua nen moi duoc
 * "lo ra" qua mot `clip-path` SVG (duong bien huu co, xem
 * `components/RouteTransitionVeil.tsx`) tien dan tu 0% den 100% dien tich
 * trong khoang `--dur-aether` (~380ms). Khi lop tren da lo HET, no duoc
 * "chot" thanh `ten` (lop duoi moi) va tu no bien mat — nguoi dung khong
 * bao gio thay mot buoc nhay.
 *
 * DIEU QUAN TRONG NHAT: `diTinh()` KHONG con lam gi cham toi VIEC DIEU
 * HUONG ca — noi dung trang (do chinh Next.js quan ly qua `{children}`) da
 * doi NGAY khi route doi, tu truoc gio, KHONG bi kho nay giu lai. Kho nay
 * chi dieu phoi HIEU UNG TRANG TRI phia sau, va hieu ung do KHOI DONG NGAY
 * o `diTinh()`, khong cho gi ca.
 *
 * KIEM THU DUOC MA KHONG CAN JSDOM: `taoRouteTransitionStore` nhan moi phu
 * thuoc cham toi trinh duyet (nap anh, hen gio, giam chuyen dong) qua tham
 * so — bo test dung `node:test` co the tiem cac ham gia, dieu khien "gio"
 * bang tay, va kiem tra CHINH XAC hieu ung co chay dung trinh tu, dung
 * nguyen tac chong-dua (race) khi dieu huong lien tiep hay khong.
 */

export type TrangThaiAether = "idle" | "revealing";

export interface RouteTransitionSnapshot {
  duongDan: string;
  /**
   * Chu de nen DA ON DINH — lop DUOI, luon hien thi day du, khong bao gio
   * bi hoat hinh. `null` truoc lan phan giai dau tien.
   */
  ten: string | null;
  /**
   * Chu de dang REVEAL — lop TREN, chi khac `null` trong luc `trangThai ===
   * "revealing"`. Khi hieu ung xong, gia tri nay duoc "chot" xuong `ten` va
   * tro lai `null`.
   */
  tenMoi: string | null;
  trangThai: TrangThaiAether;
  /**
   * The he — tang moi lan MOT LAN REVEAL MOI thuc su bat dau (khong tang
   * neu dich trung voi lan dang chay). Dung lam React `key` de bat buoc lop
   * reveal REMOUNT (va do do hoat hinh CSS restart tu 0) moi lan dieu huong
   * that su khoi dong mot chu ky moi — xem `RouteTransitionVeil.tsx`.
   */
  the: number;
}

export interface Timing {
  /** Tong thoi gian hieu ung (ms) — sau moc nay, lop reveal duoc chot thanh nen. */
  TONG: number;
}

/**
 * KHOP CHINH XAC voi `--dur-aether`/cac hang so lien quan o `globals.css` —
 * xem `route-transition-veil.test.mjs`.
 *
 * Dac ta V4: tong hieu ung 420-560ms (giam manh tu 780-900ms cua V2/V3) —
 * "must feel immediate", khong con la mot cong chan dieu huong.
 */
export const THOI_LUONG_BINH_THUONG: Timing = { TONG: 480 };
/** `prefers-reduced-motion: reduce` — bo qua Aether Rift, doi nen gan nhu
 * tuc thi (chi con mot lan mo nhe rat ngan de tranh nhay mau song). */
export const THOI_LUONG_GIAM: Timing = { TONG: 80 };

export interface RouteTransitionDeps {
  /** `tenNen` — suy chu de nen tu duong dan. */
  layTen: (duongDan: string) => string;
  /** `true` khi nguoi dung chon `prefers-reduced-motion: reduce`. */
  dangGiamChuyenDong: () => boolean;
  /**
   * Nap truoc anh cua mot chu de — V4 GOI nhung KHONG CHO (fire-and-forget,
   * chi de lam am cache trinh duyet cho lan sau); khong con quyet dinh thoi
   * diem doi anh nhu V1-V3. PHAI luon resolve (ke ca khi loi) de khong tao
   * unhandled rejection.
   */
  napAnh: (ten: string) => Promise<void>;
  datHen: (fn: () => void, ms: number) => number;
  huyHen: (id: number) => void;
}

export function taoRouteTransitionStore(deps: RouteTransitionDeps) {
  let state: RouteTransitionSnapshot = {
    duongDan: "",
    ten: null,
    tenMoi: null,
    trangThai: "idle",
    the: 0,
  };
  const nguoiNghe = new Set<() => void>();
  const henDangCho: number[] = [];
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

  /**
   * Diem vao DUY NHAT — goi moi lan phat hien `duongDan` doi (xem
   * `PageBackground.tsx`). KHONG lam cham dieu huong: chi cap nhat trang
   * thai hieu ung trang tri, tra ve ngay lap tuc.
   */
  function diTinh(duongDanMoi: string) {
    const tenMoi = deps.layTen(duongDanMoi);

    // Lan dau: chua co gi de reveal TU — hien thang, khong hieu ung.
    if (state.ten === null) {
      huyHenDangCho();
      theHe += 1;
      set({ duongDan: duongDanMoi, ten: tenMoi, tenMoi: null, trangThai: "idle", the: theHe });
      return;
    }

    // Dich trung CHINH chu de LOP DUOI (da on dinh) va KHONG co reveal nao
    // dang chay: khong co gi de lam, chi cap nhat duong dan.
    if (tenMoi === state.ten && state.trangThai === "idle") {
      set({ duongDan: duongDanMoi });
      return;
    }

    // Dich trung CHINH chu de DANG reveal: KHONG restart (tranh giat hinh
    // vo ich khi dieu huong noi bo cung mot chu de, vd `/fanfic` -> `/novels/x`).
    if (state.trangThai === "revealing" && tenMoi === state.tenMoi) {
      set({ duongDan: duongDanMoi });
      return;
    }

    // Dich trung chu de DA ON DINH trong khi mot reveal KHAC dang chay giua
    // chung: nguoi dung da doi y quay lai dung noi dang hien — huy reveal
    // do, ve idle NGAY (khong can hoan tat mot hieu ung khong con y nghia).
    if (tenMoi === state.ten && state.trangThai === "revealing") {
      huyHenDangCho();
      theHe += 1;
      set({ duongDan: duongDanMoi, tenMoi: null, trangThai: "idle", the: theHe });
      return;
    }

    // Khac chu de o CA HAI lop hien co: (khoi dong lai) MOT chu ky reveal
    // moi. Neu dang co mot reveal khac chay, no bi THAY THE hoan toan o
    // day (React se remount lop tren qua `key={the}` moi — khong xep hang,
    // khong chay song song hai hoat hinh, "newest destination wins").
    huyHenDangCho();
    theHe += 1;
    const heNay = theHe;
    const T = deps.dangGiamChuyenDong() ? THOI_LUONG_GIAM : THOI_LUONG_BINH_THUONG;

    // Lam am cache anh cho lan sau — KHONG cho, khong quyet dinh thoi diem
    // hien thi. Bat ky loi nao cung phai tu nuot (deps.napAnh da dam bao
    // luon resolve), nen khong can `.catch` o day.
    void deps.napAnh(tenMoi);

    set({ duongDan: duongDanMoi, tenMoi, trangThai: "revealing", the: theHe });

    hen(() => {
      if (heNay !== theHe) return; // co lan dieu huong khac da thay the
      set({ ten: tenMoi, tenMoi: null, trangThai: "idle" });
    }, T.TONG);
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
