"use client";

/**
 * THU VIEN — kham pha truyen cong khai + tu sach ca nhan.
 *
 * Ba muc (giu nguyen tu truoc): Fanfic & Tiểu thuyết (kho doc duoc that),
 * Sách & Tuyển tập (trang thai bien tap trung thuc, chua co an pham), Tủ sách
 * của tôi (theo doi + doc do).
 *
 * PRODUCT UX SPRINT 2 — nhung gi doi va VI SAO:
 *
 * - MOI trang thai (tim kiem, fandom, dinh dang, trang thai, sap xep, kieu
 *   xem, trang, muc) nam tren URL (`lib/libraryQuery.ts`). Chia se lien ket ra
 *   dung danh sach; Back/Forward cua trinh duyet dua ve dung bo loc truoc do.
 *   Doi bo loc = `router.push` (Back quay lai duoc); go tim = `router.replace`
 *   co tre (khong nhoi lich su tung chu cai).
 * - Mo truyen roi Back: ve GAN DUNG vi tri cuon cu (`lib/scrollMemory.ts`) —
 *   danh sach tai SAU khi trang ve nen cuon mac dinh cua Next ve dau trang.
 *   Ket qua moi bo loc duoc NHO trong bo nho 5 phut nen Back ve ngay, khong
 *   phai cho mang.
 * - Nut chinh cua moi the doc TIEN DO THAT (`lib/novelProgress.ts`):
 *   "Bắt đầu đọc" / "Đọc tiếp" / "Nghe tiếp" / "Tiếp tục" — va "tiếp" mo DUNG
 *   chuong dang do, ap vi tri da luu (`?resume=1`).
 * - Dang tai: khung xuong CUNG kich thuoc the that (khong nhay bo cuc). Ban
 *   truoc hien "Không tìm thấy tác phẩm phù hợp" trong luc DANG TAI.
 * - Loi mang: hien loi + "Thử lại". Ban truoc am tham roi ve `listNovels`
 *   (tai het khong phan trang) va giau loi.
 * - Chip fandom lay tu DU LIEU THAT (chi fandom co truyen), khong con bay chip
 *   co dinh ma phan lon bam vao ra trang rong.
 * - DUONG NHANH: kho con nho (<= 50 truyen) thi tai CA KHO mot lan va loc /
 *   sap / tim ngay tren trinh duyet. Do that tren production: bo loc fandom
 *   mat hang chuc giay o backend. Kho lon hon thi tu dung duong may chu.
 * - "Mới xuất bản" gui `sort=newest` (ban truoc gui `latest` = y het "Mới cập
 *   nhật"); "Nhiều chương" va "Tên truyện" sap tai cho (backend khong sap dung).
 * - Tren dien thoai, bo loc gon sau mot nut "Bộ lọc (n)".
 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, social, type ContinueItem, type Novel } from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { NovelCover } from "@/components/NovelCover";
import { EmptyState, ErrorState } from "@/components/ui";
import {
  IconBook,
  IconClose,
  IconGrid,
  IconHeadphones,
  IconLibrary,
  IconList,
  IconSearch,
  IconSliders,
  IconFollow,
} from "@/components/Icons";
import {
  formatChapterCount,
  isLegacyAudioOnly,
  novelFandom,
  novelHasAudio,
  novelHeroUrl,
} from "@/lib/catalog";
import { fandomCauTruc, theChoThe } from "@/lib/taxonomy";
import {
  NHAN_SAP_XEP,
  TRAN_CUC_BO,
  catTrang,
  chipFandom,
  docTuUrl,
  locToanKho,
  type CuaTruyen,
  doi,
  sapCucBo,
  sapXepCucBo,
  soBoLoc,
  thamSoDuyet,
  veUrl,
  type LocAudio,
  type LocTrangThai,
  type SapXep,
  type TabThuVien,
  type TrangThaiThuVien,
} from "@/lib/libraryQuery";
import { ghiViTri, layViTri, type KhoPhien } from "@/lib/scrollMemory";
import { taiAnhChupKho } from "@/lib/catalogSnapshot";
import { useReaderProgress } from "@/lib/useReaderProgress";
import { banGhiMoiNhat, hanhDongTruyen, type HanhDongTruyen } from "@/lib/novelProgress";
import type { BanGhiTienDo } from "@/lib/readerSession";

const KICH_THUOC_TRANG = 12;

const NHAN_TRANG_THAI: Record<string, string> = {
  ongoing: "Đang ra",
  completed: "Hoàn thành",
  hiatus: "Tạm ngưng",
};

/*
  Nam lua chon dinh dang — NGHIA THAT o `thamSoDuyet`. "Kho audio cũ" co mat
  nhung KHONG mac dinh: 13 truyen audio dai tap nhap tu kho cu khong co chu,
  nguoi doc chon thi moi thay.
*/
const LUA_CHON_AUDIO: readonly { v: LocAudio; nhan: string; goiY: string }[] = [
  { v: "all", nhan: "Tất cả", goiY: "Mọi truyện đọc được" },
  { v: "read_audio", nhan: "Đọc & nghe", goiY: "Có chữ và có audio" },
  { v: "audio", nhan: "Có audio", goiY: "Mọi truyện nghe được, kể cả kho audio cũ" },
  { v: "text", nhan: "Chỉ chữ", goiY: "Có chữ, chưa có audio" },
  { v: "legacy", nhan: "Kho audio cũ", goiY: "Truyện audio dài tập nhập từ kho cũ, không có chữ" },
];

const LUA_CHON_TRANG_THAI: readonly { v: LocTrangThai; nhan: string }[] = [
  { v: "all", nhan: "Tất cả" },
  { v: "ongoing", nhan: "Đang ra" },
  { v: "completed", nhan: "Hoàn thành" },
];

const CAC_TAB: readonly { v: TabThuVien; dai: string; ngan: string }[] = [
  { v: "fanfic", dai: "Fanfic & Tiểu thuyết", ngan: "Fanfic" },
  { v: "books", dai: "Sách & Tuyển tập", ngan: "Tuyển tập" },
  { v: "personal", dai: "Tủ sách của tôi", ngan: "Tủ sách" },
];

/* ------------------------------------------------------------ tien ich */

function khoPhien(): KhoPhien | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Ten tac gia HIEN DUOC. Rong / "Unknown Author" thi an, khong bia "Fanfic Studio". */
function tenTacGia(raw?: string | null): string | null {
  const s = (raw ?? "").trim();
  if (!s || /^(unknown|unknown author|anonymous|n\/a)$/i.test(s)) return null;
  return s;
}

function ngayNgan(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function phanTram(tiLe: number | null): number | null {
  if (tiLe === null || !Number.isFinite(tiLe)) return null;
  return Math.max(3, Math.min(100, Math.round(tiLe * 100)));
}

/* --------------------------------------------- ket qua duyet + bo nho dem */

interface KetQuaDuyet {
  novels: Novel[];
  total: number;
  /** Con truyen sau tran `limit` (chi quan trong khi sap cuc bo). */
  conNua: boolean;
}

/*
  Nho ket qua theo DUNG tham so gui len may chu. Mo truyen roi Back thi trang
  ve ngay tu day (khong khung xuong, khong cho mang) — dieu kien de khoi phuc
  vi tri cuon chinh xac. Het han 5 phut thi tai lai.
*/
const BO_NHO: Map<string, { luc: number; kq: KetQuaDuyet }> = new Map();
const HAN_BO_NHO_MS = 5 * 60 * 1000;

interface TrangThaiTai {
  khoa: string;
  kq: KetQuaDuyet | null;
  loi: string;
}

function useKetQuaDuyet(khoa: string, batDuong: boolean) {
  // Lan ve dau: co san trong bo nho thi dung luon (doc thuan, khong hieu ung).
  const [st, setSt] = useState<TrangThaiTai>(() => {
    const c = BO_NHO.get(khoa);
    return c ? { khoa, kq: c.kq, loi: "" } : { khoa: "", kq: null, loi: "" };
  });
  const [lan, setLan] = useState(0);

  useEffect(() => {
    // Duong nhanh (ca kho da o trinh duyet) dang lo: khong goi may chu.
    if (!batDuong) return;
    let huy = false;
    const c = BO_NHO.get(khoa);
    if (c && lan === 0 && Date.now() - c.luc < HAN_BO_NHO_MS) {
      void Promise.resolve().then(() => {
        if (!huy) setSt({ khoa, kq: c.kq, loi: "" });
      });
      return () => {
        huy = true;
      };
    }
    api
      .browseNovels(JSON.parse(khoa))
      .then((r) => {
        const kq: KetQuaDuyet = { novels: r.novels, total: r.total ?? r.novels.length, conNua: Boolean(r.has_more) };
        BO_NHO.set(khoa, { luc: Date.now(), kq });
        if (!huy) setSt({ khoa, kq, loi: "" });
      })
      .catch((e) => {
        // KHONG giau loi, KHONG roi ve tai het: nguoi doc thay loi va thu lai.
        if (!huy) setSt({ khoa, kq: null, loi: errorMessage(e) });
      });
    return () => {
      huy = true;
    };
  }, [khoa, lan, batDuong]);

  const thuLai = useCallback(() => {
    BO_NHO.delete(khoa);
    setSt((s) => ({ ...s, khoa: "", loi: "" }));
    setLan((x) => x + 1);
  }, [khoa]);

  return {
    kq: st.kq,
    /** Dang doi ket qua cho `khoa` hien tai (van giu ket qua cu de khong nhay). */
    dangTai: st.khoa !== khoa,
    loi: st.khoa === khoa ? st.loi : "",
    thuLai,
  };
}

/*
  MAU TOAN KHO = anh chup chung (`lib/catalogSnapshot.ts`), hai viec:
  - dung chip fandom tu du lieu that (kem so dem khi mau du ca kho);
  - DUONG NHANH: mau du ca kho (`du`) thi moi bo loc/sap xep chay tren trinh
    duyet (`locToanKho`), khong con cho may chu — xem ly do o do.
*/

/* Cach doc mot truyen cho `locToanKho` / `chipFandom` — cung nguon voi the. */
const CUA_TRUYEN: CuaTruyen<Novel> = {
  co: (n) => ({ cu: isLegacyAudioOnly(n), audio: novelHasAudio(n), status: n.status }),
  fandom: (n) => fandomCauTruc(n),
  chu: (n) => `${n.title} ${n.external_author_name ?? ""} ${n.description ?? ""}`,
  capNhat: (n) => n.updated_at || n.created_at || "",
  taoLuc: (n) => n.created_at || "",
};

/* ------------------------------------------------------------ the truyen */

interface TruyenTrenThe {
  novel_id: string;
  title: string;
  cover_url?: string | null;
  cover_portrait_url?: string | null;
  hero_background_url?: string | null;
  tags?: string[];
  fandom_ids?: string[];
  status: string;
  external_author_name?: string;
  external_chapter_count?: number;
  updated_at?: string;
  has_audio?: boolean;
  content_mode?: "readable" | "audio_only";
}

function IconHanhDong({ hd, cu }: { hd: HanhDongTruyen; cu: boolean }) {
  const nghe = cu || hd.kieu === "nghe" || hd.kieu === "ca-hai" || (hd.kieu === "xong" && hd.nhan.startsWith("Nghe"));
  return nghe ? <IconHeadphones size={15} /> : <IconBook size={15} />;
}

function TheTruyen({ n, banGhi, kieu }: { n: TruyenTrenThe; banGhi: BanGhiTienDo | null; kieu: "grid" | "list" }) {
  const coAudio = novelHasAudio(n);
  const cu = isLegacyAudioOnly(n);
  const fandom = novelFandom(n);
  const coFandom = fandom !== "Fanfic";
  const tacGia = tenTacGia(n.external_author_name);
  // Toi da HAI the, bo the trung voi fandom da hien o goc anh.
  const tags = theChoThe(n, 2, [fandom, fandomCauTruc(n)]);
  const hd = hanhDongTruyen(banGhi, { coAudio, chiAudio: cu });
  const hrefChinh = hd.href ?? `/novels/${n.novel_id}`;
  const nhanChinh = hd.kieu === "moi" ? (cu ? "Bắt đầu nghe" : "Bắt đầu đọc") : hd.nhan;
  const pct = hd.kieu === "moi" ? null : phanTram(hd.tiLe);
  const ngay = ngayNgan(n.updated_at);
  const trangThai = NHAN_TRANG_THAI[n.status] ?? n.status;

  if (kieu === "list") {
    return (
      <article className="lib-row" data-kieu={hd.kieu}>
        <NovelCover novelId={n.novel_id} title={n.title} coverUrl={n.cover_url} heroUrl={novelHeroUrl(n)} size="landscape" />
        <div className="lib-row-main">
          <h3 className="lib-row-title">
            <Link href={`/novels/${n.novel_id}`} className="lib-card-link" prefetch={false}>
              {n.title}
            </Link>
          </h3>
          <p className="lib-card-facts">
            {coFandom ? <span className="lib-fact-fandom">{fandom}</span> : null}
            {tacGia ? <span>{tacGia}</span> : null}
            <span>{formatChapterCount(n.external_chapter_count)}</span>
            <span className={`lib-fact-status status-${n.status}`}>{trangThai}</span>
            {coAudio ? (
              <span className="lib-fact-audio">
                <IconHeadphones size={13} /> Audio
              </span>
            ) : null}
          </p>
        </div>
        <Link
          href={hrefChinh}
          className={`btn btn-sm ${hd.kieu === "moi" ? "btn-outline" : "btn-primary"} lib-card-cta`}
          prefetch={false}
        >
          <IconHanhDong hd={hd} cu={cu} /> {nhanChinh}
        </Link>
      </article>
    );
  }

  return (
    <article className="lib-card" data-kieu={hd.kieu}>
      <div className="lib-card-cover-wrap">
        <NovelCover novelId={n.novel_id} title={n.title} coverUrl={n.cover_url} heroUrl={novelHeroUrl(n)} size="landscape" />
        {coFandom ? <span className="lib-card-fandom">{fandom}</span> : null}
        {pct !== null ? (
          <span className="lib-card-progress" aria-hidden="true">
            <span style={{ width: `${pct}%` }} />
          </span>
        ) : null}
      </div>
      <div className="lib-card-body">
        <h3 className="lib-card-title">
          <Link href={`/novels/${n.novel_id}`} className="lib-card-link" prefetch={false} title={n.title}>
            {n.title}
          </Link>
        </h3>
        {tacGia ? <p className="lib-card-author">{tacGia}</p> : null}
        <p className="lib-card-facts">
          <span className={`lib-fact-status status-${n.status}`}>{trangThai}</span>
          <span>{formatChapterCount(n.external_chapter_count)}</span>
          {coAudio ? (
            <span className="lib-fact-audio">
              <IconHeadphones size={13} /> Audio
            </span>
          ) : null}
        </p>
        {tags.length > 0 ? (
          <ul className="lib-card-tags" aria-label="Thể loại">
            {tags.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="lib-card-footer">
        <Link
          href={hrefChinh}
          className={`btn btn-sm ${hd.kieu === "moi" ? "btn-outline" : "btn-primary"} lib-card-cta`}
          prefetch={false}
          aria-label={`${nhanChinh}: ${n.title}`}
        >
          <IconHanhDong hd={hd} cu={cu} /> {nhanChinh}
          {pct !== null && hd.kieu !== "xong" ? <span className="lib-cta-pct">{pct}%</span> : null}
        </Link>
        {ngay ? (
          <span className="lib-card-date" title="Cập nhật lần cuối">
            {ngay}
          </span>
        ) : null}
      </div>
    </article>
  );
}

function KhungXuong({ kieu }: { kieu: "grid" | "list" }) {
  if (kieu === "list") {
    return (
      <div className="lib-rows" role="status" aria-label="Đang tải danh sách truyện">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="lib-row lib-sk" aria-hidden="true">
            <div className="sk lib-sk-thumb" />
            <div className="lib-row-main">
              <div className="sk lib-sk-line" style={{ width: "60%" }} />
              <div className="sk lib-sk-line" style={{ width: "40%" }} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="lib-story-grid" role="status" aria-label="Đang tải danh sách truyện">
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="lib-card lib-sk" aria-hidden="true">
          <div className="lib-card-cover-wrap sk" />
          <div className="lib-card-body">
            <div className="sk lib-sk-line lib-sk-title" />
            <div className="sk lib-sk-line" style={{ width: "45%" }} />
            <div className="sk lib-sk-line" style={{ width: "70%" }} />
          </div>
          <div className="lib-card-footer">
            <div className="sk lib-sk-btn" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------- dai "đọc dở" */

interface MucDocDo {
  novelId: string;
  tenTruyen: string;
  tenChuong: string | null;
  nhan: string;
  href: string;
  nghe: boolean;
  pct: number | null;
}

function dsDocDo(
  banGhi: readonly BanGhiTienDo[],
  mayChu: { reading: ContinueItem | null; listening: ContinueItem | null } | null,
  tenTheoId: ReadonlyMap<string, string>,
): MucDocDo[] {
  const ra: MucDocDo[] = [];
  const daCo = new Set<string>();
  // 1) Ban ghi tren trinh duyet nay (co ca nguoi chua dang nhap), moi -> cu.
  for (const r of banGhi) {
    if (daCo.has(r.novelId)) continue;
    daCo.add(r.novelId);
    const ten = r.tenTruyen || tenTheoId.get(r.novelId);
    if (!ten) continue;
    const hd = hanhDongTruyen(banGhiMoiNhat(banGhi, r.novelId), { coAudio: r.giay > 0 });
    if (hd.kieu === "moi" || hd.kieu === "xong" || !hd.href) continue;
    ra.push({
      novelId: r.novelId,
      tenTruyen: ten,
      tenChuong: r.tenChuong ?? null,
      nhan: hd.nhanDayDu,
      href: hd.href,
      nghe: hd.kieu !== "doc",
      pct: phanTram(hd.tiLe),
    });
  }
  // 2) Con tro cua may chu (nguoi da dang nhap, co the tu thiet bi khac).
  const them = (m: ContinueItem | null, nghe: boolean) => {
    if (!m || daCo.has(m.novel_id)) return;
    daCo.add(m.novel_id);
    const pct =
      nghe && m.position_seconds && m.duration_seconds ? phanTram(m.position_seconds / m.duration_seconds) : null;
    ra.push({
      novelId: m.novel_id,
      tenTruyen: m.novel_title,
      tenChuong: m.chapter_title ? `Chương ${m.chapter_order_index} · ${m.chapter_title}` : null,
      nhan: nghe ? "Nghe tiếp" : "Đọc tiếp",
      href: `/chapters/${m.chapter_id}?mode=${nghe ? "read_listen" : "read"}`,
      nghe,
      pct,
    });
  };
  them(mayChu?.listening ?? null, true);
  them(mayChu?.reading ?? null, false);
  return ra.slice(0, 3);
}

function DaiDocDo({ muc }: { muc: MucDocDo[] }) {
  if (muc.length === 0) return null;
  return (
    <section className="lib-continue" aria-labelledby="lib-continue-h">
      <h2 id="lib-continue-h" className="lib-section-title">
        Đang đọc dở
      </h2>
      <ul className="lib-continue-list">
        {muc.map((m) => (
          <li key={m.novelId}>
            <Link href={m.href} className="lib-continue-item" prefetch={false}>
              <span className="lib-continue-icon" aria-hidden="true">
                {m.nghe ? <IconHeadphones size={18} /> : <IconBook size={18} />}
              </span>
              <span className="lib-continue-copy">
                <strong className="clamp-1">{m.tenTruyen}</strong>
                {m.tenChuong ? <span className="clamp-1">{m.tenChuong}</span> : null}
                {m.pct !== null ? (
                  <span className="lib-continue-bar" aria-hidden="true">
                    <span style={{ width: `${m.pct}%` }} />
                  </span>
                ) : null}
              </span>
              <span className="lib-continue-cta">{m.nhan}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------ trang */

function LibraryContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { profile, loading: dangNapPhien } = useSession();
  const banGhi = useReaderProgress();

  const t = useMemo(() => docTuUrl(searchParams), [searchParams]);
  const chuoiUrl = veUrl(t);
  const urlHienTai = `${pathname}${chuoiUrl ? `?${chuoiUrl}` : ""}`;

  /* ---- ghi URL: push cho bo loc (Back quay lai duoc), replace cho go chu */
  const diToi = useCallback(
    (moi: TrangThaiThuVien, cach: "push" | "replace" = "push") => {
      const qs = veUrl(moi);
      const href = `${pathname}${qs ? `?${qs}` : ""}`;
      if (cach === "replace") router.replace(href, { scroll: false });
      else router.push(href, { scroll: false });
    },
    [pathname, router],
  );
  const dat = useCallback((phan: Partial<TrangThaiThuVien>) => diToi(doi(t, phan)), [diToi, t]);

  /* ---- o tim: trang thai tai cho, ghi len URL sau 300ms ------------------ */
  const [oTim, setOTim] = useState(t.q);
  const [qTruoc, setQTruoc] = useState(t.q);
  if (t.q !== qTruoc) {
    // URL doi tu ngoai (Back/Forward, lien ket): o tim theo URL. Chinh ta vua
    // ghi len URL (ban da cat khoang trang) thi KHONG ghi de — nguoi doc dang
    // go "hoa " ma bi mat dau cach cuoi thi chu tiep theo dinh lien.
    setQTruoc(t.q);
    if (oTim.trim() !== t.q) setOTim(t.q);
  }
  useEffect(() => {
    if (oTim.trim() === t.q) return;
    const k = window.setTimeout(() => diToi(doi(t, { q: oTim.trim() }), "replace"), 300);
    return () => window.clearTimeout(k);
  }, [oTim, t, diToi]);

  /* ---- du lieu ----------------------------------------------------------- */
  const mau = useAsyncData(taiAnhChupKho);
  // Ca kho da o trinh duyet: loc/sap tai cho, khong goi may chu nua.
  const toanKho = Boolean(mau.data?.du);

  const thamSo = useMemo(() => thamSoDuyet(t, KICH_THUOC_TRANG), [t]);
  const khoa = JSON.stringify(thamSo);
  const mayChu = useKetQuaDuyet(khoa, !toanKho);
  const kq = mayChu.kq;

  const cucBo = sapCucBo(t.sort);
  const tatCa = useMemo(() => {
    if (toanKho && mau.data) return locToanKho(mau.data.novels, t, CUA_TRUYEN);
    if (!kq) return [];
    return cucBo ? sapXepCucBo(kq.novels, t.sort) : kq.novels;
  }, [toanKho, mau.data, t, kq, cucBo]);
  const coDuLieu = toanKho || kq !== null;
  const dangTai = !toanKho && mayChu.dangTai;
  const loi = toanKho ? "" : mayChu.loi;
  // "Thử lại" nap lai CA anh chup kho neu no cung hong (khong thi chip fandom
  // va duong nhanh mat toi khi tai lai trang).
  const thuLaiMayChu = mayChu.thuLai;
  const napLaiMau = mau.reload;
  const mauRong = !mau.data?.novels.length;
  const thuLai = useCallback(() => {
    thuLaiMayChu();
    if (mauRong) napLaiMau();
  }, [thuLaiMayChu, napLaiMau, mauRong]);
  const catTaiCho = toanKho || cucBo;
  const hienThi = catTaiCho ? catTrang(tatCa, t.page, KICH_THUOC_TRANG) : tatCa;
  const tong = toanKho ? tatCa.length : (kq?.total ?? 0);
  const tongTrang = Math.max(1, Math.ceil((catTaiCho ? tatCa.length : tong) / KICH_THUOC_TRANG));
  const cucBoCat = !toanKho && cucBo && Boolean(kq?.conNua);

  const chips = useMemo(
    () => chipFandom(mau.data?.novels ?? [], CUA_TRUYEN.fandom, CUA_TRUYEN.co, t),
    [mau.data, t],
  );
  const coSoDem = toanKho;

  const napCaNhan = useCallback(async () => {
    if (!profile) return { followed: [], tiepTuc: null };
    const [f, c] = await Promise.all([
      social.followedStories(100, 0).catch(() => ({ novels: [] })),
      api.getContinueProgress().catch(() => ({ reading: null, listening: null, watching: null })),
    ]);
    return { followed: f.novels, tiepTuc: { reading: c.reading, listening: c.listening } };
    // `profile` doi danh tinh o moi lan lam moi phien; chi user_id moi quan trong.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.user_id]);
  const caNhan = useAsyncData(napCaNhan, { enabled: !dangNapPhien });

  const tenTheoId = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of mau.data?.novels ?? []) m.set(n.novel_id, n.title);
    for (const n of kq?.novels ?? []) m.set(n.novel_id, n.title);
    return m;
  }, [mau.data, kq]);
  const docDo = useMemo(
    () => dsDocDo(banGhi, caNhan.data?.tiepTuc ?? null, tenTheoId),
    [banGhi, caNhan.data, tenTheoId],
  );

  /* ---- vi tri cuon: ghi khi mo truyen, tra lai khi Back ------------------ */
  const ghiCuon = useCallback(
    (e: React.MouseEvent) => {
      const a = (e.target as HTMLElement).closest("a");
      const href = a?.getAttribute("href") ?? "";
      if (href.startsWith("/novels/") || href.startsWith("/chapters/")) {
        ghiViTri(khoPhien(), urlHienTai, window.scrollY, Date.now());
      }
    },
    [urlHienTai],
  );
  const daTraCuon = useRef(false);
  useEffect(() => {
    if (daTraCuon.current || !coDuLieu || dangTai) return;
    daTraCuon.current = true;
    const y = layViTri(khoPhien(), urlHienTai, Date.now());
    if (y === null || y <= 0) return;
    // Hai khung hinh: luoi vua ve can bo cuc xong moi du cao de cuon toi.
    requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({ top: y, behavior: "auto" })));
  }, [coDuLieu, dangTai, urlHienTai]);

  /* ---- sang trang: len dau danh sach, khong len dau trang ---------------- */
  const dauKetQua = useRef<HTMLDivElement>(null);
  const sangTrang = useCallback(
    (p: number) => {
      dat({ page: p });
      const el = dauKetQua.current;
      if (el) {
        const giam = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        const y = el.getBoundingClientRect().top + window.scrollY - 96;
        window.scrollTo({ top: Math.max(0, y), behavior: giam ? "auto" : "smooth" });
      }
    },
    [dat],
  );

  const [moLoc, setMoLoc] = useState(false);
  const soLoc = soBoLoc(t);
  const coLoc = soLoc > 0 || t.q.trim().length > 0;
  const xoaLoc = () => {
    setOTim("");
    diToi({ ...t, q: "", fandom: "all", audio: "all", status: "all", page: 1 });
  };

  const tieuDeLead =
    t.tab === "books"
      ? "Tuyển tập và ấn phẩm tuyển chọn đang được biên soạn."
      : t.tab === "personal"
        ? "Truyện bạn theo dõi và những chương đang đọc dở."
        : "Truyện chữ và fanfic chuyển ngữ tiếng Việt — đọc, nghe, hoặc vừa đọc vừa nghe.";

  const locAudioHienTai = LUA_CHON_AUDIO.find((x) => x.v === t.audio);

  return (
    <div className="page stack-3 lib-page" data-hero-theme="library" onClickCapture={ghiCuon}>
      <header className="ent-header lib-header">
        <div className="ent-header-copy">
          <div className="ent-header-eyebrow">
            <IconLibrary size={13} />
            <span>Fanfic World</span>
          </div>
          <h1 className="ent-header-title">Thư viện</h1>
          <p className="ent-header-lead">{tieuDeLead}</p>
        </div>

        <nav className="lib-tabs" aria-label="Phân mục thư viện">
          {CAC_TAB.map((tab) => {
            const dangChon = t.tab === tab.v;
            const dem =
              tab.v === "fanfic" && t.tab === "fanfic" && coDuLieu && !dangTai
                ? tong
                : tab.v === "personal" && profile && caNhan.data
                  ? caNhan.data.followed.length
                  : null;
            return (
              <button
                key={tab.v}
                type="button"
                className={`lib-tab${dangChon ? " is-active" : ""}`}
                aria-current={dangChon ? "page" : undefined}
                onClick={() => dat({ tab: tab.v })}
              >
                {tab.v === "fanfic" ? (
                  <IconBook size={15} />
                ) : tab.v === "books" ? (
                  <IconLibrary size={15} />
                ) : (
                  <IconFollow size={15} />
                )}
                <span className="lib-tab-dai">
                  {tab.v === "fanfic" ? (
                    <>Fanfic &amp; Tiểu thuyết</>
                  ) : tab.v === "books" ? (
                    <>Sách &amp; Tuyển tập</>
                  ) : (
                    <>Tủ sách của tôi</>
                  )}
                </span>
                <span className="lib-tab-ngan">{tab.ngan}</span>
                {dem !== null ? <span className="lib-tab-dem">{dem}</span> : null}
              </button>
            );
          })}
        </nav>
      </header>

      <div key={t.tab} className="ent-tab-panel">
        {t.tab === "fanfic" ? (
          <div className="stack-3">
            <DaiDocDo muc={docDo} />

            {/* ---- tim + sap xep + kieu xem ---- */}
            <div className="lib-toolbar" role="search">
              <label className="lib-search">
                <IconSearch size={17} className="lib-search-icon" />
                <span className="sr-only">Tìm trong thư viện</span>
                <input
                  type="search"
                  value={oTim}
                  onChange={(e) => setOTim(e.target.value)}
                  placeholder="Tìm tên truyện, tác giả, mô tả…"
                  enterKeyHint="search"
                  autoComplete="off"
                  maxLength={120}
                />
                {oTim ? (
                  <button
                    type="button"
                    className="lib-search-clear"
                    onClick={() => setOTim("")}
                    aria-label="Xoá từ khoá"
                  >
                    <IconClose size={15} />
                  </button>
                ) : null}
              </label>

              <button
                type="button"
                className={`btn btn-sm lib-filter-toggle${moLoc ? " is-open" : ""}`}
                aria-expanded={moLoc}
                aria-controls="lib-filters"
                onClick={() => setMoLoc((x) => !x)}
              >
                <IconSliders size={16} /> Bộ lọc{soLoc > 0 ? ` (${soLoc})` : ""}
              </button>

              <label className="lib-sort">
                <span className="lib-sort-label">Sắp xếp</span>
                <select
                  value={t.sort}
                  onChange={(e) => dat({ sort: e.target.value as SapXep })}
                  aria-label="Sắp xếp truyện"
                >
                  {(Object.keys(NHAN_SAP_XEP) as SapXep[]).map((s) => (
                    <option key={s} value={s}>
                      {NHAN_SAP_XEP[s]}
                    </option>
                  ))}
                </select>
              </label>

              <div className="lib-view" role="group" aria-label="Kiểu hiển thị">
                <button
                  type="button"
                  className={`lib-view-btn${t.view === "grid" ? " is-active" : ""}`}
                  aria-pressed={t.view === "grid"}
                  onClick={() => dat({ view: "grid" })}
                  title="Dạng lưới"
                >
                  <IconGrid size={16} />
                  <span className="sr-only">Dạng lưới</span>
                </button>
                <button
                  type="button"
                  className={`lib-view-btn${t.view === "list" ? " is-active" : ""}`}
                  aria-pressed={t.view === "list"}
                  onClick={() => dat({ view: "list" })}
                  title="Dạng danh sách"
                >
                  <IconList size={16} />
                  <span className="sr-only">Dạng danh sách</span>
                </button>
              </div>
            </div>

            {/* ---- bo loc: luon hien o may tinh, gon sau nut tren dien thoai ---- */}
            <div id="lib-filters" className="lib-filters" data-mo={moLoc ? "1" : "0"}>
              {/* Dinh dang + trang thai chung MOT hang tren man hinh rong (tu xuong dong khi hep). */}
              <div className="lib-filter-pair">
                <div className="lib-filter-line" role="group" aria-labelledby="lib-f-dinhdang">
                  <span id="lib-f-dinhdang" className="lib-filter-label">
                    Định dạng
                  </span>
                  <div className="lib-chips">
                    {LUA_CHON_AUDIO.map((o) => (
                      <button
                        key={o.v}
                        type="button"
                        className={`lib-chip${t.audio === o.v ? " is-active" : ""}${o.v === "legacy" ? " lib-chip-phu" : ""}`}
                        aria-pressed={t.audio === o.v}
                        title={o.goiY}
                        onClick={() => dat({ audio: o.v })}
                      >
                        {o.v === "read_audio" || o.v === "audio" || o.v === "legacy" ? (
                          <IconHeadphones size={13} />
                        ) : null}
                        {o.v === "text" ? <IconBook size={13} /> : null}
                        {o.nhan}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="lib-filter-line" role="group" aria-labelledby="lib-f-trangthai">
                  <span id="lib-f-trangthai" className="lib-filter-label lib-filter-label-gon">
                    Trạng thái
                  </span>
                  <div className="lib-chips">
                    {LUA_CHON_TRANG_THAI.map((o) => (
                      <button
                        key={o.v}
                        type="button"
                        className={`lib-chip${t.status === o.v ? " is-active" : ""}`}
                        aria-pressed={t.status === o.v}
                        onClick={() => dat({ status: o.v })}
                      >
                        {o.nhan}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="lib-filter-line" role="group" aria-labelledby="lib-f-fandom">
                <span id="lib-f-fandom" className="lib-filter-label">
                  Fandom
                </span>
                <div className="lib-chips">
                  <button
                    type="button"
                    className={`lib-chip${t.fandom === "all" ? " is-active" : ""}`}
                    aria-pressed={t.fandom === "all"}
                    onClick={() => dat({ fandom: "all" })}
                  >
                    Tất cả
                  </button>
                  {chips.map((c) => (
                    <button
                      key={c.ten}
                      type="button"
                      className={`lib-chip${t.fandom === c.ten ? " is-active" : ""}`}
                      aria-pressed={t.fandom === c.ten}
                      onClick={() => dat({ fandom: t.fandom === c.ten ? "all" : c.ten })}
                    >
                      {c.ten}
                      {coSoDem ? <span className="lib-chip-dem">{c.so}</span> : null}
                    </button>
                  ))}
                  {mau.loading && chips.length === 0 ? (
                    <span className="sk lib-sk-chip" aria-hidden="true" />
                  ) : null}
                </div>
              </div>
            </div>

            {/* ---- dang loc gi (de thay ca khi bo loc dang gon tren dien thoai) ---- */}
            {coLoc ? (
              <div className="lib-active" aria-label="Bộ lọc đang bật">
                {t.q ? (
                  <button type="button" className="lib-active-chip" onClick={() => { setOTim(""); dat({ q: "" }); }}>
                    “{t.q}” <IconClose size={13} />
                    <span className="sr-only">Bỏ từ khoá</span>
                  </button>
                ) : null}
                {t.fandom !== "all" ? (
                  <button type="button" className="lib-active-chip" onClick={() => dat({ fandom: "all" })}>
                    {t.fandom} <IconClose size={13} />
                    <span className="sr-only">Bỏ lọc fandom</span>
                  </button>
                ) : null}
                {t.audio !== "all" ? (
                  <button type="button" className="lib-active-chip" onClick={() => dat({ audio: "all" })}>
                    {locAudioHienTai?.nhan} <IconClose size={13} />
                    <span className="sr-only">Bỏ lọc định dạng</span>
                  </button>
                ) : null}
                {t.status !== "all" ? (
                  <button type="button" className="lib-active-chip" onClick={() => dat({ status: "all" })}>
                    {NHAN_TRANG_THAI[t.status]} <IconClose size={13} />
                    <span className="sr-only">Bỏ lọc trạng thái</span>
                  </button>
                ) : null}
                <button type="button" className="lib-active-clear" onClick={xoaLoc}>
                  Xoá bộ lọc
                </button>
              </div>
            ) : null}

            {/* ---- ket qua ---- */}
            <section className="stack-2" aria-labelledby="lib-results-h" aria-busy={dangTai}>
              <div className="lib-results-head" ref={dauKetQua}>
                <h2 id="lib-results-h" className="lib-section-title">
                  {t.audio === "legacy" ? "Kho audio cũ" : "Truyện"}
                </h2>
                <p className="lib-results-count" aria-live="polite">
                  {!coDuLieu ? "Đang tải…" : `${tong} truyện · ${NHAN_SAP_XEP[t.sort]}`}
                  {dangTai && coDuLieu ? <span className="lib-results-loading"> · đang cập nhật…</span> : null}
                </p>
              </div>

              {loi ? (
                <ErrorState message={loi} onRetry={thuLai} />
              ) : !coDuLieu ? (
                <KhungXuong kieu={t.view} />
              ) : hienThi.length === 0 ? (
                <EmptyState
                  icon="🔍"
                  title={t.q ? `Không có truyện nào khớp “${t.q}”` : "Không có truyện nào khớp bộ lọc này"}
                  hint={
                    t.audio === "text"
                      ? "Hiện mọi truyện đọc được đều đã có audio. Thử “Tất cả” hoặc “Đọc & nghe”."
                      : "Thử bỏ bớt bộ lọc, hoặc tìm bằng tên tác giả."
                  }
                  action={
                    coLoc ? (
                      <button type="button" className="btn btn-primary" onClick={xoaLoc}>
                        Xoá bộ lọc
                      </button>
                    ) : undefined
                  }
                />
              ) : (
                <div className={`lib-results${dangTai ? " is-stale" : ""}`}>
                  {t.view === "grid" ? (
                    <div className="lib-story-grid">
                      {hienThi.map((n) => (
                        <TheTruyen key={n.novel_id} n={n} banGhi={banGhiMoiNhat(banGhi, n.novel_id)} kieu="grid" />
                      ))}
                    </div>
                  ) : (
                    <div className="lib-rows">
                      {hienThi.map((n) => (
                        <TheTruyen key={n.novel_id} n={n} banGhi={banGhiMoiNhat(banGhi, n.novel_id)} kieu="list" />
                      ))}
                    </div>
                  )}
                  {cucBoCat ? (
                    <p className="hint lib-note">
                      Đang sắp xếp {TRAN_CUC_BO} truyện đầu tiên theo “{NHAN_SAP_XEP[t.sort]}”.
                    </p>
                  ) : null}
                </div>
              )}

              {coDuLieu && !loi && tongTrang > 1 ? (
                <nav className="lib-pagination" aria-label="Phân trang">
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={t.page <= 1 || dangTai}
                    onClick={() => sangTrang(t.page - 1)}
                  >
                    ← Trang trước
                  </button>
                  <span className="lib-page-of">
                    Trang {t.page} / {tongTrang}
                  </span>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={t.page >= tongTrang || dangTai}
                    onClick={() => sangTrang(t.page + 1)}
                  >
                    Trang sau →
                  </button>
                </nav>
              ) : null}
            </section>
          </div>
        ) : t.tab === "books" ? (
          <EmptyState
            icon="📚"
            title="Tuyển tập & Tuyển tập đặc biệt đang được tuyển chọn"
            hint="Đội ngũ biên tập đang chuẩn bị các tuyển tập fanfic, sách văn học và tác phẩm chuyển thể theo chủ đề. Không có dữ liệu giả lập — ấn phẩm sẽ xuất hiện ở đây khi biên tập xong."
            action={
              <button type="button" className="btn btn-primary" onClick={() => dat({ tab: "fanfic" })}>
                <IconBook size={15} /> Khám phá Fanfic &amp; Tiểu thuyết
              </button>
            }
          />
        ) : (
          <div className="stack-3">
            <DaiDocDo muc={docDo} />
            {dangNapPhien ? (
              <KhungXuong kieu="grid" />
            ) : !profile ? (
              <div className="lib-guest-banner" role="status">
                <div className="lib-guest-text">
                  <strong>Đăng nhập để có tủ sách riêng</strong>
                  <p>Theo dõi truyện yêu thích và đồng bộ chỗ đang đọc, đang nghe trên mọi thiết bị.</p>
                </div>
                {/*
                  KHONG co nut "đăng nhập nhanh" nao o day. Ban truoc gan cung
                  email + mat khau that vao nut nay, khong co dieu kien moi
                  truong, nen chuoi mat khau nam trong bundle production cong
                  khai (do 2026-09-25). Dang nhap chi qua /login.
                */}
                <Link className="btn btn-primary btn-sm" href="/login?next=/library?tab=personal" prefetch={false}>
                  Đăng nhập
                </Link>
              </div>
            ) : caNhan.error ? (
              <ErrorState message={caNhan.error} onRetry={caNhan.reload} />
            ) : !caNhan.data ? (
              <KhungXuong kieu="grid" />
            ) : caNhan.data.followed.length === 0 ? (
              <EmptyState
                icon="⭐"
                title="Tủ sách của bạn chưa có truyện nào"
                hint="Bấm “Theo dõi” ở trang truyện để lưu vào đây và biết khi có chương mới."
                action={
                  <button type="button" className="btn btn-primary" onClick={() => dat({ tab: "fanfic" })}>
                    <IconBook size={15} /> Khám phá truyện
                  </button>
                }
              />
            ) : (
              <section className="stack-2" aria-labelledby="lib-follow-h">
                <div className="lib-results-head">
                  <h2 id="lib-follow-h" className="lib-section-title">
                    Đang theo dõi
                  </h2>
                  <p className="lib-results-count">{caNhan.data.followed.length} truyện</p>
                </div>
                <div className="lib-story-grid">
                  {caNhan.data.followed.map((n) => (
                    <TheTruyen key={n.novel_id} n={n} banGhi={banGhiMoiNhat(banGhi, n.novel_id)} kieu="grid" />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ThuVienPage() {
  return (
    <Suspense
      fallback={
        <div className="page stack-3 lib-page" data-hero-theme="library">
          <KhungXuong kieu="grid" />
        </div>
      }
    >
      <LibraryContent />
    </Suspense>
  );
}
