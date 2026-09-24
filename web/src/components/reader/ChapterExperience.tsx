"use client";

/**
 * TRAI NGHIEM CHUONG THONG NHAT — doc va nghe tren MOT trang `/chapters/[id]`,
 * MOT dong co (`AudioEngine`, the `<audio>` duy nhat trong layout).
 *
 * Truoc sprint nay doc va nghe la HAI trang: `/chapters/[id]` chi chu,
 * `/listen/[id]` chi nghe (overnight Phase 2A). Nguoi vua doc vua nghe phai
 * chon mot, va doan dang doc khong bao gio sang len trong cot chu. Gio:
 *
 *   - "read"        — chi chu, khong trinh phat noi.
 *   - "read_listen" — chu + trinh phat noi o day + to sang doan dang doc +
 *                     "Theo giọng đọc".
 *   - "listen"      — trinh phat lon o dau + khung chu mo / thu gon / dong.
 *
 * `/listen/[id]` chuyen huong ve day (`?mode=listen`), lien ket cu van chay.
 *
 * Ba bat bien:
 *   1. KHONG tu phat khi mo trang. Chi phat khi nguoi dung bam (Phat, Tiếp
 *      tục nghe, Nghe từ đoạn này, Chương sau LUC DANG NGHE) hoac URL xin
 *      tuong minh (`?autoplay=1`) — va trinh duyet chan thi thoi, khong bao loi.
 *   2. KHONG giang trang khi nguoi dung dang tu cuon (xem `lib/followScroll.ts`).
 *   3. An chu, thu nho trinh phat, doi che do Nghe <-> Doc+Nghe: KHONG BAO GIO
 *      dung audio. Chi "Đọc" (chi doc) moi tam dung — do la y nguoi dung.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { createPortal } from "react-dom";
import { api, type TranscriptSegment } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAudioEngine, dongHo } from "@/components/AudioEngine";
import { ChapterPlayer } from "@/components/ChapterPlayer";
import { ListenReporter } from "@/components/ListenReporter";
import { ContinueListenReporter } from "@/components/ContinueListenReporter";
import { SyncedTranscript } from "@/components/SyncedTranscript";
import { ChapterReaderPrefsControl } from "@/components/ChapterInteractiveReader";
import { EmptyState } from "@/components/ui";
import {
  IconArrowDown,
  IconArrowUp,
  IconBook,
  IconHeadphones,
  IconTextShow,
} from "@/components/Icons";
import { doanDangDoc, giayBatDauDoan, lapMoHinh } from "@/lib/chapterSync";
import {
  cheDoBanDau,
  congTacDangBat,
  khiBamCongTac,
  khiNguoiDungCuon,
  khiToiDoanDangDoc,
  kieuCuon,
  laCuonTay,
  nutToiDoan,
  trongVungDoc,
  viTriCuonDich,
  type CheDoTheo,
  type KhungNhin,
} from "@/lib/followScroll";
import {
  chuoiGhiCookie,
  deXuatTiepTuc,
  docTienDo,
  ghiTienDo,
  type CheDoDoc,
  type DeXuatTiepTuc,
  type KhoLuu,
  type KhungChu,
  type TuyChonCheDo,
} from "@/lib/readerSession";
import { ChapterAudioDock } from "./ChapterAudioDock";
import { ReaderText } from "./ReaderText";
import { ChapterContext, ChapterNavLink, type ChuongLienKe } from "./ChapterNavLink";

export interface ChapterExperienceProps {
  chapterId: string;
  chapterTitle: string;
  novelId: string;
  novelTitle: string;
  coverUrl?: string | null;
  paragraphs: string[];
  hasAudio: boolean;
  audioOutdated: boolean;
  /** Da phan giai o may chu: URL > cookie > mac dinh (`readerSession.cheDoKhiMo`). */
  initialMode: CheDoDoc;
  initialPrefs: TuyChonCheDo;
  /** `?autoplay=1` — yeu cau phat TUONG MINH tren URL. */
  urlRequestsPlay: boolean;
  prev: ChuongLienKe | null;
  next: ChuongLienKe | null;
  /** Chu chuong — de chi duong "Tạo lại audio" khi audio da cu (M4). */
  ownerId?: string;
  /** Phan con lai cua trang (Hoi AI, binh luan, dieu huong) — nam TRONG ngu
      canh de lien ket chuong biet "dang nghe". */
  children?: React.ReactNode;
}

/* ------------------------------------------------------------ tien ich nho */

function khoLuu(): KhoLuu | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

const TRUY_VAN_GIAM = "(prefers-reduced-motion: reduce)";
function dangKyGiam(f: () => void): () => void {
  const mq = window.matchMedia?.(TRUY_VAN_GIAM);
  mq?.addEventListener?.("change", f);
  return () => mq?.removeEventListener?.("change", f);
}
function useGiamChuyenDong(): boolean {
  return useSyncExternalStore(
    dangKyGiam,
    () => !!window.matchMedia?.(TRUY_VAN_GIAM).matches,
    () => false,
  );
}

/*
  Da o trinh duyet chua (sau hydrate). Anh chup may chu `false`, nen HTML may
  chu va lan ve dau khop nhau, roi React ve lai voi `true`.
*/
const khongDangKy = () => () => {};
function useDaMount(): boolean {
  return useSyncExternalStore(khongDangKy, () => true, () => false);
}

/** Phan tren bi thanh dau trang dinh che. */
function caoDauTrang(): number {
  const h = document.querySelector<HTMLElement>(".site-header");
  if (!h) return 0;
  const r = h.getBoundingClientRect();
  return r.bottom > 0 ? Math.min(r.bottom, 120) : 0;
}

const NHAN_CHE_DO: Record<CheDoDoc, string> = {
  read: "Đọc",
  read_listen: "Đọc + Nghe",
  listen: "Nghe",
};

/* ------------------------------------------------------------ component */

export function ChapterExperience(props: ChapterExperienceProps) {
  const {
    chapterId,
    chapterTitle,
    novelId,
    novelTitle,
    coverUrl,
    paragraphs,
    hasAudio,
    audioOutdated,
    initialMode,
    initialPrefs,
    urlRequestsPlay,
    prev,
    next,
    ownerId,
    children,
  } = props;

  const router = useRouter();
  const { profile } = useSession();
  const isOwner = !!ownerId && profile?.user_id === ownerId;
  const { trangThai: t, dieuKhien: d } = useAudioEngine();
  const giamChuyenDong = useGiamChuyenDong();
  const daMount = useDaMount();
  const coChu = paragraphs.length > 0;

  const [mode, setMode] = useState<CheDoDoc>(initialMode);
  const [prefs, setPrefs] = useState<TuyChonCheDo>(initialPrefs);
  // Lua chon da luu thang; chua tung chon thi theo `prefers-reduced-motion`
  // (anh chup may chu luon `false`, nen lan ve dau khop HTML may chu).
  const [theoTay, setTheoTay] = useState<CheDoTheo | null>(null);
  const theo: CheDoTheo = theoTay ?? cheDoBanDau(giamChuyenDong, initialPrefs.theoGiong);
  const [phuDe, setPhuDe] = useState<TranscriptSegment[] | null>(null);
  const [doanChon, setDoanChon] = useState(-1);
  const [deXuat, setDeXuat] = useState<DeXuatTiepTuc | null>(null);
  const [huongNut, setHuongNut] = useState<"len" | "xuong" | null>(null);
  const [xaDau, setXaDau] = useState(false);
  const [heroKhuat, setHeroKhuat] = useState(false);
  /** Nguoi dung mo rong trinh phat khi CHUA nghe (xem truoc) — chi trong phien. */
  const [moRong, setMoRong] = useState(false);

  const cotChu = useRef<HTMLElement | null>(null);
  const hero = useRef<HTMLDivElement | null>(null);
  const dock = useRef<HTMLDivElement | null>(null);
  const caoDock = useRef(0);

  /* ------------------------------------------------- engine <-> chuong nay */

  const laBaiNay = t.chapterId === chapterId;
  /** Engine dang ban MOT CHUONG KHAC (da bam nghe) — khong duoc tu y cuop. */
  const banChuongKhac = !!t.chapterId && !laBaiNay && t.daBatDau;
  const dangNghe = laBaiNay && t.daBatDau;
  const thongTin = useMemo(
    () => ({ tieuDeTruyen: novelTitle, anhBia: coverUrl ?? null }),
    [novelTitle, coverUrl],
  );

  /* --------------------------------------------------------------- dong bo */

  const moHinh = useMemo(() => lapMoHinh(paragraphs, phuDe), [paragraphs, phuDe]);
  const doanDoc = dangNghe ? doanDangDoc(moHinh, t.thoiDiem, t.thoiLuong) : -1;

  // Phu de that (neu co) — mot GET nhe, `available:false` thi dung uoc luong.
  useEffect(() => {
    if (!hasAudio || !coChu) return;
    let huy = false;
    api
      .getChapterTranscript(chapterId)
      .then((r) => {
        if (!huy && r.available) setPhuDe(r.segments);
      })
      .catch(() => {});
    return () => {
      huy = true;
    };
  }, [chapterId, hasAudio, coChu]);

  /* ------------------------------------------------------------ luu lua chon */

  const luuPrefs = useCallback((moi: TuyChonCheDo) => {
    setPrefs(moi);
    try {
      document.cookie = chuoiGhiCookie(moi, location.protocol === "https:");
    } catch {
      /* Cookie bi chan: lua chon van co hieu luc trong phien nay. */
    }
  }, []);

  const doiCheDo = useCallback(
    (m: CheDoDoc) => {
      setMode(m);
      luuPrefs({ ...prefs, cheDo: m });
      // "Đọc" = chi doc: tam dung giong doc cua CHINH chuong nay (khong dung
      // chuong khac dang phat o thanh toan cuc).
      if (m === "read" && laBaiNay && t.dangPhat) d.tamDung();
      // Chuyen sang che do co nghe: nap san audio neu engine dang ranh, de bam
      // phat la chay ngay va biet thoi luong. KHONG phat.
      if (m !== "read" && hasAudio && (!t.chapterId || (!laBaiNay && !t.daBatDau))) {
        d.phat(chapterId, chapterTitle, thongTin);
      }
    },
    [prefs, luuPrefs, laBaiNay, t.dangPhat, t.chapterId, t.daBatDau, hasAudio, d, chapterId, chapterTitle, thongTin],
  );

  const doiKhungChu = useCallback(
    (k: KhungChu) => luuPrefs({ ...prefs, khungChu: k }),
    [prefs, luuPrefs],
  );

  const doiThuNho = useCallback(
    (v: boolean) => luuPrefs({ ...prefs, thuNho: v }),
    [prefs, luuPrefs],
  );

  const doiTheo = useCallback(() => {
    const moi = khiBamCongTac(theo);
    setTheoTay(moi);
    luuPrefs({ ...prefs, theoGiong: congTacDangBat(moi) });
  }, [theo, prefs, luuPrefs]);

  /** "Ẩn truyện chữ" o Doc+Nghe = sang Nghe voi chu dong; "Hiện" = mo khung. */
  const doiHienChu = useCallback(
    (hien: boolean) => {
      if (hien) {
        if (mode === "listen") doiKhungChu("open");
        return;
      }
      setMode("listen");
      luuPrefs({ ...prefs, cheDo: "listen", khungChu: "closed" });
      // Chu vua an, trang ngan lai: dua trinh phat lon vao tam mat thay vi de
      // nguoi dung dung o giua khoang trong phia duoi.
      requestAnimationFrame(() =>
        hero.current?.scrollIntoView({ block: "start", behavior: kieuCuon(giamChuyenDong) }),
      );
    },
    [mode, prefs, luuPrefs, doiKhungChu, giamChuyenDong],
  );

  /* ------------------------------------------------------ phat theo nghia trang */

  /** Nut Phat cua TRANG: chuong nay dang nap -> bat/tat; chua -> nap + phat. */
  const bamPhat = useCallback(() => {
    if (!hasAudio) return;
    if (laBaiNay && t.tep) {
      d.batTat();
    } else {
      d.phat(chapterId, chapterTitle, { ...thongTin, tuPhat: true });
    }
    if (mode === "read") {
      setMode("read_listen");
      luuPrefs({ ...prefs, cheDo: "read_listen" });
    }
  }, [hasAudio, laBaiNay, t.tep, d, chapterId, chapterTitle, thongTin, mode, prefs, luuPrefs]);

  /** Giao audio cho chuong dich TRUOC khi dieu huong — xem `ChapterNavLink`. */
  const giaoAudio = useCallback(
    (dich: ChuongLienKe, epNghe = false) => {
      const dangPhatBaiNay = laBaiNay && t.dangPhat;
      if ((dangPhatBaiNay || epNghe) && dich.has_audio !== false) {
        d.phat(dich.chapter_id, dich.title, { ...thongTin, tuPhat: true });
      }
    },
    [laBaiNay, t.dangPhat, d, thongTin],
  );

  const sangChuong = useCallback(
    (dich: ChuongLienKe | null, epNghe = false) => {
      if (!dich) return;
      giaoAudio(dich, epNghe);
      if (epNghe && mode === "read") luuPrefs({ ...prefs, cheDo: "read_listen" });
      router.push(`/chapters/${dich.chapter_id}`);
    },
    [giaoAudio, mode, prefs, luuPrefs, router],
  );

  const ngheTuDoan = useCallback(
    (i: number) => {
      setDoanChon(-1);
      const giay = giayBatDauDoan(moHinh, i, laBaiNay ? t.thoiLuong : 0);
      if (laBaiNay && t.tep && giay !== null) {
        void d.tua(giay);
        if (!t.dangPhat) d.choPhat();
      } else {
        // Chua nap / chua biet thoi luong: nap + phat; uoc luong vi tri sau.
        d.phat(chapterId, chapterTitle, { ...thongTin, tuPhat: true, batDauTu: giay ?? undefined });
      }
      setTheoTay("theo");
    },
    [moHinh, laBaiNay, t.thoiLuong, t.tep, t.dangPhat, d, chapterId, chapterTitle, thongTin],
  );

  /* ----------------------------------------------------- mo trang: nap / xin phat */

  const daKhoiDong = useRef(false);
  useEffect(() => {
    if (daKhoiDong.current || !hasAudio) return;
    daKhoiDong.current = true;
    if (urlRequestsPlay && !banChuongKhac) {
      d.phat(chapterId, chapterTitle, { ...thongTin, tuPhat: true });
      return;
    }
    // Nap san (KHONG phat) khi che do co nghe va engine ranh.
    if (initialMode !== "read" && (!t.chapterId || (!laBaiNay && !t.daBatDau))) {
      d.phat(chapterId, chapterTitle, thongTin);
    }
    // Chi chay MOT lan luc mo trang — cac lan sau do nguoi dung quyet dinh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* -------------------------------------------------------- tiep tuc doc/nghe */

  useEffect(() => {
    const r = docTienDo(khoLuu(), chapterId);
    const dx = deXuatTiepTuc(r, { coAudio: hasAudio, soDoan: paragraphs.length, bayGio: Date.now() });
    if (!dx) return;
    // Dang nghe song chuong nay roi (quay lai trong cung phien): khong moi.
    const moi: DeXuatTiepTuc = { doc: dx.doc, nghe: dangNghe ? null : dx.nghe };
    if (!moi.doc && !moi.nghe) return;
    queueMicrotask(() => setDeXuat(moi));
    // Chi doc MOT lan luc mo trang.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId]);

  const khungNhin = useCallback((): KhungNhin => ({
    cao: window.innerHeight,
    tren: caoDauTrang(),
    duoi: caoDock.current,
  }), []);

  const theDoan = useCallback(
    (i: number) => cotChu.current?.querySelector<HTMLElement>(`[data-doan="${i}"]`) ?? null,
    [],
  );

  const cuonToiDoan = useCallback(
    (i: number, truot: boolean) => {
      const el = theDoan(i);
      if (!el) return;
      const k = khungNhin();
      window.scrollTo({
        top: viTriCuonDich(el.getBoundingClientRect(), window.scrollY, k),
        behavior: truot ? kieuCuon(giamChuyenDong) : "auto",
      });
    },
    [theDoan, khungNhin, giamChuyenDong],
  );

  const tiepTucDoc = useCallback(() => {
    if (!deXuat?.doc) return;
    const i = deXuat.doc.doan;
    setDeXuat(null);
    if (mode === "listen" && prefs.khungChu !== "open") doiKhungChu("open");
    // Doi mot khung hinh: khung chu vua mo can bo cuc xong moi do duoc vi tri.
    requestAnimationFrame(() => cuonToiDoan(i, true));
  }, [deXuat, mode, prefs.khungChu, doiKhungChu, cuonToiDoan]);

  const tiepTucNghe = useCallback(() => {
    if (!deXuat?.nghe) return;
    const giay = deXuat.nghe.giay;
    setDeXuat(null);
    d.phat(chapterId, chapterTitle, { ...thongTin, batDauTu: giay, tuPhat: true });
    if (mode === "read") {
      setMode("read_listen");
      luuPrefs({ ...prefs, cheDo: "read_listen" });
    }
    setTheoTay("theo");
  }, [deXuat, d, chapterId, chapterTitle, thongTin, mode, prefs, luuPrefs]);

  /* ------------------------------------------------------------- hien chu? */

  // Chu hien (du dai) o Doc va Doc+Nghe; o Nghe tuy khung.
  const hienChuDay = coChu && (mode !== "listen" || prefs.khungChu === "open");
  const coTrinhPhatNoi =
    hasAudio && !banChuongKhac && (mode === "read_listen" || (mode === "listen" && heroKhuat && dangNghe));

  /* ------------------------------------------------ theo giong doc: tu cuon */

  useEffect(() => {
    if (doanDoc < 0 || theo !== "theo" || !hienChuDay) return;
    const el = theDoan(doanDoc);
    if (!el) return;
    const k = khungNhin();
    const hop = el.getBoundingClientRect();
    if (trongVungDoc(hop, k)) return;
    window.scrollTo({ top: viTriCuonDich(hop, window.scrollY, k), behavior: kieuCuon(giamChuyenDong) });
  }, [doanDoc, theo, hienChuDay, theDoan, khungNhin, giamChuyenDong]);

  // Nguoi dung TU cuon -> tam dung theo doi. Nhan dien bang Y DINH, khong
  // bang su kien `scroll` (lenh cuon cua chinh ta cung ban `scroll`).
  const modeRef = useRef(mode);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    if (!dangNghe) return;
    const khiNhap = (e: Event) => {
      const dich = e.target as HTMLElement | null;
      if (dich?.closest?.("[data-khong-tinh-cuon]")) return;
      const ke = e as KeyboardEvent;
      // Space o che do Nghe la phim Phat/Tam dung (xem phim tat), khong cuon.
      if (e.type === "keydown" && ke.key === " " && modeRef.current === "listen") return;
      if (
        laCuonTay({
          type: e.type,
          key: ke.key,
          tagName: dich?.tagName,
          isContentEditable: dich?.isContentEditable,
          ctrlKey: ke.ctrlKey,
          metaKey: ke.metaKey,
          altKey: ke.altKey,
          laGocTaiLieu: dich === document.documentElement,
        })
      ) {
        setTheoTay((s) => khiNguoiDungCuon(s ?? cheDoBanDau(giamChuyenDong, initialPrefs.theoGiong)));
      }
    };
    const tuyChon = { passive: true } as const;
    window.addEventListener("wheel", khiNhap, tuyChon);
    window.addEventListener("touchmove", khiNhap, tuyChon);
    window.addEventListener("keydown", khiNhap);
    window.addEventListener("pointerdown", khiNhap, tuyChon);
    return () => {
      window.removeEventListener("wheel", khiNhap);
      window.removeEventListener("touchmove", khiNhap);
      window.removeEventListener("keydown", khiNhap);
      window.removeEventListener("pointerdown", khiNhap);
    };
  }, [dangNghe, giamChuyenDong, initialPrefs.theoGiong]);

  const toiDoanDangDoc = useCallback(() => {
    setTheoTay(khiToiDoanDangDoc());
    if (doanDoc >= 0) cuonToiDoan(doanDoc, true);
  }, [doanDoc, cuonToiDoan]);

  const lenDauTrang = useCallback(() => {
    window.scrollTo({ top: 0, behavior: kieuCuon(giamChuyenDong) });
  }, [giamChuyenDong]);

  /* ------------------------------------ cuon: nut noi + luu vi tri doc (rAF) */

  const doanDocRef = useRef(doanDoc);
  const theoRef = useRef(theo);
  useEffect(() => {
    doanDocRef.current = doanDoc;
    theoRef.current = theo;
  }, [doanDoc, theo]);

  const tinhNut = useCallback(() => {
    setXaDau(window.scrollY > window.innerHeight * 1.2);
    const i = doanDocRef.current;
    const el = i >= 0 ? theDoan(i) : null;
    setHuongNut(
      nutToiDoan(theoRef.current, {
        dangNghe,
        hienChu: hienChuDay && modeRef.current !== "read",
        doan: i,
        hop: el ? el.getBoundingClientRect() : null,
        k: khungNhin(),
      }),
    );
  }, [dangNghe, hienChuDay, theDoan, khungNhin]);

  useEffect(() => {
    let khung = 0;
    let henLuu = 0;
    const luuViTri = () => {
      if (!cotChu.current || !hienChuDay) return;
      const ps = cotChu.current.querySelectorAll<HTMLElement>("[data-doan]");
      if (ps.length === 0) return;
      const tren = caoDauTrang() + 8;
      // Tim nhi phan doan dau tien con thay (cac doan xep theo thu tu tren trang).
      let lo = 0;
      let hi = ps.length - 1;
      let kq = ps.length - 1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (ps[mid].getBoundingClientRect().bottom > tren) {
          kq = mid;
          hi = mid - 1;
        } else {
          lo = mid + 1;
        }
      }
      // Chua cuon toi cot chu: vi tri doc la 0.
      const doan = cotChu.current.getBoundingClientRect().top > tren ? 0 : kq;
      ghiTienDo(khoLuu(), chapterId, novelId, { doan, tongDoan: ps.length, cheDo: mode }, Date.now());
    };
    const nhip = () => {
      if (!khung) {
        khung = requestAnimationFrame(() => {
          khung = 0;
          tinhNut();
        });
      }
      window.clearTimeout(henLuu);
      henLuu = window.setTimeout(luuViTri, 900);
    };
    window.addEventListener("scroll", nhip, { passive: true });
    window.addEventListener("resize", nhip);
    nhip();
    return () => {
      window.removeEventListener("scroll", nhip);
      window.removeEventListener("resize", nhip);
      if (khung) cancelAnimationFrame(khung);
      window.clearTimeout(henLuu);
    };
  }, [tinhNut, hienChuDay, chapterId, novelId, mode]);

  // Doan doi hoac theo doi doi cung phai tinh lai nut (khong cho cuon).
  useEffect(() => {
    const k = requestAnimationFrame(tinhNut);
    return () => cancelAnimationFrame(k);
  }, [doanDoc, theo, tinhNut]);

  /* --------------------------------------------------- luu vi tri audio (5s) */

  const giayDaLuu = useRef(-100);
  useEffect(() => {
    if (!laBaiNay || !t.daBatDau) return;
    const giay = t.thoiDiem;
    const dungLai = !t.dangPhat;
    if (!dungLai && Math.abs(giay - giayDaLuu.current) < 5) return;
    giayDaLuu.current = giay;
    ghiTienDo(khoLuu(), chapterId, novelId, { giay, thoiLuong: t.thoiLuong, cheDo: mode }, Date.now());
  }, [laBaiNay, t.daBatDau, t.thoiDiem, t.dangPhat, t.thoiLuong, chapterId, novelId, mode]);

  /* ------------------------------------------ trinh phat lon con thay khong */

  useEffect(() => {
    const el = hero.current;
    if (!el || mode !== "listen") return;
    const theoDoi = new IntersectionObserver(
      ([muc]) => setHeroKhuat(!muc.isIntersecting),
      { rootMargin: "-72px 0px 0px 0px" },
    );
    theoDoi.observe(el);
    return () => theoDoi.disconnect();
  }, [mode]);

  /* ------------------------------ chieu cao trinh phat noi -> dem cuoi trang */

  useEffect(() => {
    const el = dock.current;
    const body = document.body;
    if (!coTrinhPhatNoi || !el) {
      caoDock.current = 0;
      body.classList.remove("co-dock");
      body.style.removeProperty("--dock-cao");
      return;
    }
    const capNhat = () => {
      const h = Math.ceil(el.getBoundingClientRect().height) + 16;
      caoDock.current = h;
      body.style.setProperty("--dock-cao", `${h}px`);
    };
    body.classList.add("co-dock");
    capNhat();
    const ro = new ResizeObserver(capNhat);
    ro.observe(el);
    return () => {
      ro.disconnect();
      body.classList.remove("co-dock");
      body.style.removeProperty("--dock-cao");
    };
  }, [coTrinhPhatNoi, prefs.thuNho, daMount]);

  /* ----------------------------------------------------------- phim tat */

  useEffect(() => {
    if (!hasAudio) return;
    const khiPhim = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      const dich = e.target as HTMLElement | null;
      const tag = dich?.tagName ?? "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || dich?.isContentEditable) return;
      const k = e.key;
      if (k === "Escape") {
        setDoanChon(-1);
      } else if (k === "k" || k === "K" || (k === " " && mode === "listen" && tag !== "BUTTON" && tag !== "A")) {
        e.preventDefault();
        // Dang phat chuong KHAC: phim tat dieu khien cai dang phat, khong tu
        // y doi sang chuong nay (nut "Nghe chương này" moi lam viec do).
        if (banChuongKhac) d.batTat();
        else bamPhat();
      } else if ((k === "j" || k === "J") && laBaiNay) {
        d.tuaTuongDoi(-10);
      } else if ((k === "l" || k === "L") && laBaiNay) {
        d.tuaTuongDoi(10);
      }
    };
    window.addEventListener("keydown", khiPhim);
    return () => window.removeEventListener("keydown", khiPhim);
  }, [hasAudio, mode, bamPhat, laBaiNay, banChuongKhac, d]);

  /* ------------------------------------ chuong truoc/sau tu tai nghe / man khoa */

  useEffect(() => {
    if (!laBaiNay || typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    const dat = (ten: MediaSessionAction, fn: (() => void) | null) => {
      try {
        ms.setActionHandler(ten, fn);
      } catch {
        /* khong ho tro */
      }
    };
    dat("previoustrack", prev ? () => sangChuong(prev, true) : null);
    dat("nexttrack", next ? () => sangChuong(next, true) : null);
    return () => {
      dat("previoustrack", null);
      dat("nexttrack", null);
    };
  }, [laBaiNay, prev, next, sangChuong]);

  /* ---------------------------------------------------------------- ve */

  const ngu = useMemo(() => ({ giaoAudio: (dich: ChuongLienKe) => giaoAudio(dich) }), [giaoAudio]);
  /** Cham lai doan dang chon = bo chon. */
  const chonDoan = useCallback((i: number) => setDoanChon((c) => (c === i ? -1 : i)), []);
  const coTheNgheTuDoan = hasAudio && mode !== "read" && !banChuongKhac;
  const hienToSang = mode !== "read";

  const cheDoCoNghe = hasAudio && coChu;
  const noiDungChu = coChu ? (
    <ReaderText
      paragraphs={paragraphs}
      activeIdx={hienToSang ? doanDoc : -1}
      selectedIdx={doanChon}
      canSeek={coTheNgheTuDoan}
      onSelect={chonDoan}
      onListenFrom={ngheTuDoan}
    />
  ) : null;

  return (
    <ChapterContext.Provider value={ngu}>
      <div className="reader-toolbar">
        {cheDoCoNghe ? (
          <div className="reader-modes" role="group" aria-label="Chế độ đọc và nghe">
            {(["read", "read_listen", "listen"] as const).map((m) => (
              <button
                key={m}
                type="button"
                className={`reader-mode${mode === m ? " is-active" : ""}`}
                aria-pressed={mode === m}
                onClick={() => doiCheDo(m)}
              >
                {m === "read" ? <IconBook size={15} /> : <IconHeadphones size={15} />}
                {NHAN_CHE_DO[m]}
              </button>
            ))}
          </div>
        ) : null}
        {coChu ? <ChapterReaderPrefsControl /> : null}
      </div>

      {banChuongKhac && hasAudio && mode !== "read" ? (
        <div className="reader-notice" role="status">
          <span>
            Đang phát chương khác. Trình phát ở cuối màn hình vẫn điều khiển chương đó.
          </span>
          <button type="button" className="btn btn-sm btn-primary" onClick={bamPhat}>
            <IconHeadphones size={15} /> Nghe chương này
          </button>
        </div>
      ) : null}

      {deXuat ? (
        <div className="reader-resume" role="region" aria-label="Tiếp tục từ lần trước">
          <span className="reader-resume-text">
            {deXuat.nghe && deXuat.doc
              ? `Lần trước bạn dừng ở đoạn ${deXuat.doc.doan + 1}/${deXuat.doc.tongDoan}, audio ${dongHo(deXuat.nghe.giay)}.`
              : deXuat.nghe
                ? `Lần trước bạn nghe tới ${dongHo(deXuat.nghe.giay)}.`
                : `Lần trước bạn đọc tới đoạn ${deXuat.doc!.doan + 1}/${deXuat.doc!.tongDoan}.`}
          </span>
          <span className="reader-resume-actions">
            {deXuat.doc ? (
              <button type="button" className="btn btn-sm" onClick={tiepTucDoc}>
                <IconBook size={15} /> Tiếp tục đọc
              </button>
            ) : null}
            {deXuat.nghe ? (
              <button type="button" className="btn btn-sm btn-primary" onClick={tiepTucNghe}>
                <IconHeadphones size={15} /> Tiếp tục nghe
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => setDeXuat(null)}
              aria-label="Bỏ qua gợi ý tiếp tục"
            >
              ✕
            </button>
          </span>
        </div>
      ) : null}

      {/* ------------------------------------------- che do Nghe: trinh phat lon */}
      {mode === "listen" && hasAudio ? (
        <div className="listen-col reader-hero" ref={hero}>
          {/* M4: canh bao NGAY TREN trinh phat — nguoi sap bam phat can biet
              audio co the lech chu. Khong bao gio dan toi xoa audio. */}
          {audioOutdated ? (
            <div className="alert alert-warn" role="status">
              <span aria-hidden="true">⚠</span>
              <span className="stack-2">
                <span>
                  Chương này đã được sửa sau khi tạo audio, nên{" "}
                  <strong>audio có thể không còn khớp</strong> với nội dung mới. Bản audio hiện
                  tại vẫn nghe và tải được.
                </span>
                {/* Nut that, khong phai lien ket trong cau (M4): vung bam
                    du to o mobile, va duong dan sang cho tao lai phai RO. */}
                {isOwner ? (
                  <Link className="btn btn-sm" href="/studio/write" prefetch={false}>
                    Tạo lại audio trong khu vực tác giả
                  </Link>
                ) : null}
              </span>
            </div>
          ) : null}
          {laBaiNay ? (
            <ChapterPlayer
              novelId={novelId}
              novelTitle={novelTitle}
              coverUrl={coverUrl}
              chapterTitle={chapterTitle}
              onTruoc={prev ? () => sangChuong(prev) : undefined}
              onSau={next ? () => sangChuong(next) : undefined}
            />
          ) : (
            <section className="listen-hero reader-hero-idle" aria-label="Nghe chương này">
              <p className="hint">Nghe bản audio của chương này.</p>
              <button type="button" className="btn btn-primary" onClick={bamPhat}>
                <IconHeadphones size={15} /> Nghe chương này
              </button>
            </section>
          )}
        </div>
      ) : null}

      {/* ------------------------------------------------------------ cot chu */}
      {mode === "listen" && coChu ? (
        <div className="reader-drawer-head" data-khung={prefs.khungChu}>
          <span className="reader-drawer-title">
            <IconBook size={16} /> Truyện chữ
          </span>
          <div className="reader-drawer-ctl" role="group" aria-label="Hiển thị truyện chữ">
            {(
              [
                ["open", "Mở"],
                ["collapsed", "Thu gọn"],
                ["closed", "Đóng"],
              ] as const
            ).map(([k, nhan]) => (
              <button
                key={k}
                type="button"
                className={`btn btn-sm ${prefs.khungChu === k ? "btn-primary" : "btn-ghost"}`}
                aria-pressed={prefs.khungChu === k}
                onClick={() => doiKhungChu(k)}
              >
                {nhan}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {mode === "listen" && coChu && prefs.khungChu === "collapsed" ? (
        <section className="reader reader-now" aria-label="Đoạn đang đọc">
          <p className="reader-now-text">
            {paragraphs[doanDoc >= 0 ? doanDoc : 0]}
          </p>
          <button type="button" className="btn btn-sm" onClick={() => doiKhungChu("open")}>
            <IconTextShow size={15} /> Hiện truyện chữ
          </button>
        </section>
      ) : null}

      {mode === "listen" && coChu && prefs.khungChu === "closed" ? (
        <div className="reader-closed">
          <button type="button" className="btn btn-sm" onClick={() => doiKhungChu("open")}>
            <IconTextShow size={15} /> Hiện truyện chữ
          </button>
        </div>
      ) : null}

      {/*
        Cot chu LUON nam trong DOM (ke ca khi khung chu dang dong/thu gon) —
        chi an bang `hidden`. SEO van thay chu, mo lai tuc thi, va vi tri cac
        doan khong bi dung lai tu dau moi lan mo.
      */}
      <section
        className="reader"
        aria-label="Nội dung chương"
        ref={cotChu}
        hidden={coChu && !hienChuDay}
        data-to-sang={hienToSang && dangNghe ? "" : undefined}
      >
        {coChu ? (
          noiDungChu
        ) : hasAudio ? (
          <EmptyState
            icon="🎧"
            title="Chương này chỉ có bản audio"
            hint={`Chưa có bản chữ cho chương này${novelTitle ? ` trong ${novelTitle}` : ""}. Bấm Phát ở trình phát phía trên để nghe trọn chương.`}
          />
        ) : (
          <p className="hint">Chương này chưa có nội dung.</p>
        )}
      </section>

      {!coChu && hasAudio ? (
        <section className="stack-2 listen-col" aria-label="Phụ đề đồng bộ">
          <h2 className="section-title">Phụ đề</h2>
          <SyncedTranscript chapterId={chapterId} />
        </section>
      ) : null}

      {/* ------------------------------------------------------- het chuong */}
      <section className="reader-end" aria-label="Hết chương">
        <span className="eyebrow">Hết chương</span>
        {next ? (
          <div className="reader-end-actions">
            <ChapterNavLink
              target={next}
              href={`/chapters/${next.chapter_id}`}
              className="btn btn-primary reader-end-next"
              rel="next"
            >
              <span className="reader-end-label">
                <span className="reader-end-cap">Chương tiếp theo</span>
                <span className="truncate reader-end-title">{next.title}</span>
              </span>
              <span aria-hidden="true">→</span>
            </ChapterNavLink>
            {hasAudio && next.has_audio !== false ? (
              <button type="button" className="btn reader-end-listen" onClick={() => sangChuong(next, true)}>
                <IconHeadphones size={15} /> Nghe tiếp chương sau
              </button>
            ) : null}
          </div>
        ) : (
          <p className="hint">Bạn đã tới chương mới nhất hiện có.</p>
        )}
      </section>

      {children}

      {/*
        Nut noi + trinh phat noi di qua PORTAL vao `<body>`. Do duoc
        2026-09-24: `.page` giu `transform` sau hoat anh vao trang
        (`vao-trang ... both`), va mot to tien co `transform` bien
        `position: fixed` thanh "co dinh theo to tien do" — trinh phat noi
        nam o CUOI trang (y = 17.325px) thay vi day man hinh. Portal thoat
        khoi moi to tien, hom nay lan sau nay. Ngu canh React van di qua.
      */}
      {daMount && (huongNut || xaDau) ? createPortal(
        <div className="reader-chips" data-khong-tinh-cuon="">
          {huongNut ? (
            <button type="button" className="reader-chip reader-chip-main" onClick={toiDoanDangDoc}>
              {huongNut === "len" ? <IconArrowUp size={15} /> : <IconArrowDown size={15} />}
              Tới đoạn đang đọc
            </button>
          ) : null}
          {xaDau ? (
            <button
              type="button"
              className="reader-chip"
              onClick={lenDauTrang}
              aria-label="Lên đầu trang"
              title="Lên đầu trang"
            >
              <IconArrowUp size={15} />
            </button>
          ) : null}
        </div>,
        document.body,
      ) : null}

      {/* ----------------------------------------------------- trinh phat noi */}
      {daMount && coTrinhPhatNoi ? createPortal(
        <ChapterAudioDock
          ref={dock}
          novelId={novelId}
          novelTitle={novelTitle}
          coverUrl={coverUrl}
          chapterTitle={chapterTitle}
          laBaiNay={laBaiNay}
          // Chua nghe o Doc+Nghe: mac dinh la vien nho "Nghe chương này" — chu
          // chiem man hinh, trinh phat khong chan duong nguoi chi muon doc.
          thuNho={prefs.thuNho || (mode === "read_listen" && !dangNghe && !moRong)}
          onThuNho={(v) => {
            if (!dangNghe) {
              // Chua nghe: mo rong chi de xem truoc, KHONG tu phat.
              setMoRong(!v);
              if (!v && prefs.thuNho) doiThuNho(false);
              return;
            }
            doiThuNho(v);
          }}
          onPhat={bamPhat}
          coTruoc={!!prev}
          coSau={!!next}
          onTruoc={() => sangChuong(prev)}
          onSau={() => sangChuong(next)}
          theoBat={congTacDangBat(theo)}
          onTheo={doiTheo}
          coChu={coChu}
          hienChu={hienChuDay}
          onHienChu={doiHienChu}
          uocLuong={!moHinh.coPhuDe}
        />,
        document.body,
      ) : null}

      {laBaiNay && hasAudio ? (
        <>
          <ListenReporter chapterId={chapterId} />
          {profile ? <ContinueListenReporter novelId={novelId} chapterId={chapterId} /> : null}
        </>
      ) : null}
    </ChapterContext.Provider>
  );
}
