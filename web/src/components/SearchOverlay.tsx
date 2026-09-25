"use client";

/**
 * TIM KIEM TOAN CUC — truyen, nguoi dung, tac gia.
 *
 * VAN DE DA CO: o tim o header chi DIEU HUONG sang `/fanfic?q=...`. Dung cho
 * truyen, nhung tu khi co trang ca nhan thi khong con du: go ten mot nguoi vao
 * do se ra "khong tim thay truyen nao", va nguoi dung khong co cach nao biet
 * rang ho dang tim sai cho.
 *
 * BA quyet dinh:
 *
 *   1. TIM O MAY CHU. Tai het nguoi dung ve roi loc o trinh duyet la vua cham
 *      vua la mot cach tai ca danh ba nguoi dung ve may khach.
 *   2. GIAM NHIP go phim. Ban 250ms; khong co no thi mot cau bay chu la bay
 *      request, va sau cai bi bo di ngay khi den.
 *   3. HUY request cu. Ket qua ve khong theo thu tu gui: mot truy van "na" cham
 *      co the ve SAU "nam" va ghi de ket qua dung. `AbortController` cat viec do
 *      tu goc.
 *
 * BAN PHIM: Escape dong va tra tieu diem ve o nhap, mui ten len/xuong di giua
 * cac ket qua, Enter mo ket qua dang chon. `role="combobox"` +
 * `aria-activedescendant` de trinh doc man hinh doc duoc muc dang chon ma tieu
 * diem van o o nhap.
 *
 * PRODUCT UX SPRINT 2:
 *   - GOI Y TUC THI tu anh chup kho (`lib/catalogSnapshot.ts` +
 *     `lib/searchSuggest.ts`): fandom ("nar" -> Naruto), TAC GIA (backend
 *     khong tim theo tac gia) va ten truyen khong phan biet dau — hien NGAY
 *     trong luc backend (do that: vai giay moi truy van) con dang tra loi.
 *     Ket qua day du van cua backend.
 *   - Enter khi CHUA chon muc nao = xem moi ket qua trong Thu vien
 *     (`/library?q=`); mui ten xuong moi chon muc dau. Ban truoc muc dau luon
 *     "dang chon" nen Enter mo thang truyen dau tien, ke ca khi nguoi doc chi
 *     muon tim.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  api,
  social,
  type AnimationSeries,
  type Novel,
  type Post,
  type PublicProfile,
} from "@/lib/api";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { Avatar } from "@/components/Avatar";
import { fandomCauTruc, getReaderTags, theChoThe } from "@/lib/taxonomy";
import { NovelCover } from "@/components/NovelCover";
import {
  IconBook,
  IconFeather,
  IconFilm,
  IconHeadphones,
  IconMegaphone,
  IconSearch,
  IconTag,
  IconUser,
} from "@/components/Icons";
import { taiAnhChupKho, type AnhChupKho } from "@/lib/catalogSnapshot";
import { chipFandom, chuanHoaTim, MAC_DINH_THU_VIEN } from "@/lib/libraryQuery";
import { boTrungTheoId, goiYTimKiem, gopTruyen } from "@/lib/searchSuggest";
import { isLegacyAudioOnly, novelHasAudio } from "@/lib/catalog";

const NHIP_GO = 250;

type NovelAudio = Novel & { audio_chapter_count: number };

type KetQua =
  | { loai: "fandom"; ten: string; so: number }
  | { loai: "tacgia"; ten: string; so: number }
  | { loai: "truyen"; novel: Novel }
  | { loai: "nguoi"; nguoi: PublicProfile }
  | { loai: "bai"; bai: Post }
  | { loai: "audio"; novel: NovelAudio }
  | { loai: "animation"; series: AnimationSeries };

type TrangThai = "dau" | "dang-tai" | "co" | "rong" | "loi";

/**
 * Bo chon danh muc tim kiem (Phan F, V4 visual completion).
 *
 * MOT DANG KY — khong phai mot lan viet lai `SearchOverlay`. Them "Animation"
 * that khi V6 co du lieu chi la them MOT dong o day roi bat `sanSang`, KHONG
 * dung mot truy van/nhanh hien thi rieng.
 *
 * "audio" da that (V4 visual completion, vong 2, Buoc 11): `GET
 * /api/search/audio` tim truyen DA XUAT BAN va CO it nhat mot chuong da co
 * ban audio, dan ve trang truyen (kien truc hien tai chua co trang nghe
 * rieng — do la viec cua ban thiet ke lai sau nay, khong lam o day).
 *
 * "animation" (V6, overnight Phase 5) da that: `GET /api/search/animation`
 * tim SERIES DA XUAT BAN, dan ve trang series (`/animation/{id}`).
 */
const DANH_MUC: ReadonlyArray<{
  khoa: "tat_ca" | "truyen" | "nguoi" | "bai" | "audio" | "animation";
  nhan: string;
  sanSang: boolean;
}> = [
  { khoa: "tat_ca", nhan: "Tất cả", sanSang: true },
  { khoa: "truyen", nhan: "Truyện", sanSang: true },
  { khoa: "audio", nhan: "Audio", sanSang: true },
  { khoa: "nguoi", nhan: "Người dùng", sanSang: true },
  { khoa: "bai", nhan: "Bài đăng", sanSang: true },
  { khoa: "animation", nhan: "Animation", sanSang: true },
];
type DanhMuc = (typeof DANH_MUC)[number]["khoa"];

export function SearchOverlay({
  mo,
  onDong,
}: {
  mo: boolean;
  onDong: () => void;
}) {
  const router = useRouter();
  const idGoc = useId();
  const oNhap = useRef<HTMLInputElement | null>(null);
  const [q, setQ] = useState("");
  /*
    Ket qua LUON di kem tu khoa da sinh ra no.

    Nho vay trang thai hien thi duoc SUY RA thay vi luu them: neu `ketQua.tu`
    khac tu khoa dang go thi ta biet minh dang cho, ma khong can mot bien
    `dangTai` phai dat va xoa dung cho. Va quan trong han: than effect khong con
    goi `setState` dong bo nao — quy tac `react-hooks/set-state-in-effect` cam
    dieu do, va o day no chi thang tay mot thiet ke von da thua trang thai.
  */
  const [ketQua, setKetQua] = useState<{
    tu: string;
    truyen: Novel[];
    nguoi: PublicProfile[];
    bai: Post[];
    audio: NovelAudio[];
    animation: AnimationSeries[];
  } | null>(null);
  const [tuLoi, setTuLoi] = useState("");
  // -1 = CHUA chon muc nao: Enter tim trong Thu vien, khong mo truyen dau.
  const [chon, setChon] = useState(-1);
  const [danhMuc, setDanhMuc] = useState<DanhMuc>("tat_ca");
  const [kho, setKho] = useState<AnhChupKho | null>(null);

  const tu = q.trim();
  const KHONG: never[] = useMemo(() => [], []);
  const coMayChu = ketQua?.tu === tu;
  const truyenMayChu = coMayChu ? ketQua.truyen : KHONG;
  const nguoi = coMayChu ? ketQua.nguoi : KHONG;
  const bai = coMayChu ? ketQua.bai : KHONG;
  const audioMayChu = coMayChu ? ketQua.audio : KHONG;
  const animation = coMayChu ? ketQua.animation : KHONG;

  /* Goi y tai cho (fandom / tac gia / ten truyen) — chi o "Tất cả" va "Truyện". */
  const goiY = useMemo(
    () =>
      danhMuc === "tat_ca" || danhMuc === "truyen"
        ? goiYTimKiem(tu, kho?.novels ?? KHONG, {
            fandomCua: fandomCauTruc,
            chuanHoa: chuanHoaTim,
            // So dem fandom = so truyen Thu vien SE HIEN khi bam (kho doc duoc).
            demFandom: (n) => !isLegacyAudioOnly(n),
          })
        : { fandom: KHONG, tacGia: KHONG, truyen: KHONG },
    [tu, kho, danhMuc, KHONG],
  );
  const gioiHanHien = danhMuc === "tat_ca" ? 5 : 20;
  const truyen = useMemo(
    () => (coMayChu ? gopTruyen(truyenMayChu, goiY.truyen, gioiHanHien) : goiY.truyen),
    [coMayChu, truyenMayChu, goiY.truyen, gioiHanHien],
  );
  // Nhom Audio chi giu truyen CHUA hien o nhom Truyen.
  const audio = useMemo(() => boTrungTheoId(audioMayChu, truyen), [audioMayChu, truyen]);
  const fandomGoiY = goiY.fandom;
  const tacGiaGoiY = goiY.tacGia;
  const coGoiY = fandomGoiY.length + tacGiaGoiY.length + goiY.truyen.length > 0;
  // Dang cho backend (ke ca khi da co goi y tai cho de hien).
  const choMayChu = !!tu && !coMayChu && tuLoi !== tu;

  const trangThai: TrangThai = !tu
    ? "dau"
    : tuLoi === tu && !coGoiY
      ? "loi"
      : !coMayChu && !coGoiY
        ? "dang-tai"
        : truyen.length + nguoi.length + bai.length + audio.length + animation.length + fandomGoiY.length + tacGiaGoiY.length
          ? "co"
          : "rong";

  /* Fandom pho bien (khi chua go gi): tu anh chup, pham vi doc duoc mac dinh. */
  const fandomPhoBien = useMemo(
    () =>
      chipFandom(
        kho?.novels ?? KHONG,
        fandomCauTruc,
        (n: Novel) => ({ cu: isLegacyAudioOnly(n), audio: novelHasAudio(n), status: n.status }),
        MAC_DINH_THU_VIEN,
      ).slice(0, 6),
    [kho, KHONG],
  );

  useEffect(() => {
    // Anh chup kho chi tai khi o tim MO lan dau (dung chung voi Thu vien).
    if (!mo || kho) return;
    let huy = false;
    void taiAnhChupKho().then((k) => {
      if (!huy) setKho(k);
    });
    return () => {
      huy = true;
    };
  }, [mo, kho]);

  /* -- tim -------------------------------------------------------------- */

  useEffect(() => {
    if (!mo || !tu) return;

    /*
      Chon mot danh muc CU THE thi chi hoi dung ho do — vua nhanh hon (bot
      request thua), vua cho phep lay NHIEU ket qua hon cho danh muc dang
      xem (khong con chia canh voi hai ho kia).
      */
    const canTruyen = danhMuc === "tat_ca" || danhMuc === "truyen";
    const canNguoi = danhMuc === "tat_ca" || danhMuc === "nguoi";
    const canBai = danhMuc === "tat_ca" || danhMuc === "bai";
    const canAudio = danhMuc === "tat_ca" || danhMuc === "audio";
    const canAnimation = danhMuc === "tat_ca" || danhMuc === "animation";
    const gioiHan = danhMuc === "tat_ca" ? 5 : 20;

    const bo = new AbortController();
    const hen = window.setTimeout(async () => {
      try {
        /*
          NAM truy van SONG SONG. Tuan tu thi nguoi dung cho tong thoi gian cua
          ca nam, va muc cuoi luon toi muon han mot nhip.
        */
        /*
          Bai dang, audio, animation la muc PHU khi xem "Tất cả": loi cua rieng
          chung khong duoc keo sap ca hop tim — truyen va nguoi van la ly do
          nguoi ta mo hop nay. `catch` tra ve rong thay vi de `Promise.all` tu
          choi tat ca.
        */
        const [a, b, c, d, e] = await Promise.all([
          canTruyen
            ? api.browseNovels({ query: tu, limit: gioiHan })
            : Promise.resolve({ novels: [] }),
          canNguoi
            ? api.searchPeople(tu, "users", gioiHan)
            : Promise.resolve({ people: [] }),
          canBai
            ? social.searchPosts(tu, gioiHan).catch(() => ({ items: [], total: 0 }))
            : Promise.resolve({ items: [], total: 0 }),
          canAudio
            ? api.searchAudio(tu, gioiHan).catch(() => ({ novels: [] }))
            : Promise.resolve({ novels: [] }),
          canAnimation
            ? api.searchAnimation(tu, gioiHan).catch(() => ({ series: [] }))
            : Promise.resolve({ series: [] }),
        ]);
        if (bo.signal.aborted) return;
        setKetQua({
          tu, truyen: a.novels, nguoi: b.people, bai: c.items, audio: d.novels,
          animation: e.series,
        });
      } catch {
        if (!bo.signal.aborted) setTuLoi(tu);
      }
    }, NHIP_GO);

    return () => {
      bo.abort();
      window.clearTimeout(hen);
    };
  }, [tu, mo, danhMuc]);

  /* -- ban phim --------------------------------------------------------- */

  const danh: KetQua[] = useMemo(
    () => [
      ...fandomGoiY.map((f) => ({ loai: "fandom" as const, ten: f.ten, so: f.so })),
      ...tacGiaGoiY.map((a) => ({ loai: "tacgia" as const, ten: a.ten, so: a.so })),
      ...truyen.map((n) => ({ loai: "truyen" as const, novel: n })),
      ...audio.map((n) => ({ loai: "audio" as const, novel: n })),
      ...animation.map((s) => ({ loai: "animation" as const, series: s })),
      ...nguoi.map((p) => ({ loai: "nguoi" as const, nguoi: p })),
      ...bai.map((b) => ({ loai: "bai" as const, bai: b })),
    ],
    [fandomGoiY, tacGiaGoiY, truyen, audio, animation, nguoi, bai],
  );
  /* Vi tri bat dau cua tung nhom trong `danh` (cho id/aria cua tung dong). */
  const bd = {
    tacgia: fandomGoiY.length,
    truyen: fandomGoiY.length + tacGiaGoiY.length,
    audio: fandomGoiY.length + tacGiaGoiY.length + truyen.length,
    animation: fandomGoiY.length + tacGiaGoiY.length + truyen.length + audio.length,
    nguoi: fandomGoiY.length + tacGiaGoiY.length + truyen.length + audio.length + animation.length,
    bai:
      fandomGoiY.length + tacGiaGoiY.length + truyen.length + audio.length + animation.length + nguoi.length,
  };

  const duong = useCallback((k: KetQua) => {
    if (k.loai === "fandom") return `/library?fandom=${encodeURIComponent(k.ten)}`;
    if (k.loai === "tacgia") return `/library?q=${encodeURIComponent(k.ten)}`;
    if (k.loai === "truyen" || k.loai === "audio") return `/novels/${k.novel.novel_id}`;
    if (k.loai === "animation") return `/animation/${k.series.series_id}`;
    if (k.loai === "bai") return `/posts/${k.bai.post_id}`;
    return `/u/${k.nguoi.username}`;
  }, []);

  useEffect(() => {
    if (!mo) return;
    const phim = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onDong();
        return;
      }
      if (e.key === "Enter") {
        // Tieu diem dang o mot lien ket/nut (Tab toi) thi de no tu xu ly.
        if (e.target !== oNhap.current) return;
        // Chua chon muc nao: xem moi ket qua trong Thu vien.
        const muc = chon >= 0 ? danh[chon] : undefined;
        if (!muc && !tu) return;
        e.preventDefault();
        router.push(muc ? duong(muc) : `/library?q=${encodeURIComponent(tu)}`);
        onDong();
        return;
      }
      if (!danh.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setChon((c) => (c + 1) % danh.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setChon((c) => (c <= 0 ? danh.length - 1 : c - 1));
      }
    };
    window.addEventListener("keydown", phim);
    return () => window.removeEventListener("keydown", phim);
  }, [mo, danh, chon, duong, router, onDong, tu]);

  useEffect(() => {
    // Tieu diem vao o nhap ngay khi mo. Khong co buoc nay thi nguoi dung ban
    // phim phai Tab qua ca thanh dieu huong moi go duoc.
    // BOI DEN tu khoa cu: go tiep la THAY the, khong noi vao duoi ("nar" +
    // "corty" = "narcorty" — loi do duoc o QA Sprint 2). Muon sua tu cu thi
    // bam mui ten/chuot nhu moi o nhap.
    if (mo) {
      oNhap.current?.focus();
      oNhap.current?.select();
    }
  }, [mo]);

  if (!mo) return null;

  /*
    `createPortal` vao `document.body` — KHONG render tai cho `SearchOverlay`
    duoc goi (ben trong `SiteSearch` -> `SiteHeader`, xem `layout.tsx`).

    VAN DE DA CO: `.site-header` co `backdrop-filter` (xem globals.css), va
    theo dac ta CSS mot phan tu co `backdrop-filter` tro thanh containing
    block cho MOI hau due `position: fixed`. `.tim-lop` dung `position: fixed;
    inset: 0` de phu kin man hinh — nhung khi no la hau due cua `.site-header`,
    "man hinh" cua no bi tinh lai thanh KHUNG CUA HEADER, khong phai khung
    nhin that. Ket qua: hop tim khong con phu kin man hinh ma chi la mot dai
    ngang nam duoi thanh dieu huong.

    `createPortal` dua cay DOM cua overlay ra ngoai, thanh con truc tiep cua
    `<body>` — khong con containing block nao cua header can duong nua, du cay
    REACT (props/state/context) khong doi.
  */
  return createPortal(
    <div
      className="tim-lop"
      role="dialog"
      aria-modal="true"
      aria-label="Tìm kiếm"
      onMouseDown={(e) => {
        // Bam ra NGOAI hop thi dong. `mousedown` chu khong phai `click`: bam giu
        // roi keo tu trong hop ra ngoai khong duoc tinh la mot lan bam ra ngoai.
        if (e.target === e.currentTarget) onDong();
      }}
    >
      <div className="tim-hop kinh">
        <div className="tim-dau">
          {/* SEARCHING: mot chi bao nho BEN TRONG (16px), khong phai ca khung
              tim quay — xem phan hoi thiet ke tai `docs/design/` va lich su
              o day: ban truoc tung xoay ca vien hop tim, nguoi dung khong
              muon vay. */}
          {trangThai === "dang-tai" || choMayChu ? (
            <span className="spinner" aria-hidden="true" />
          ) : (
            <IconSearch size={18} />
          )}
          {/* Bo chon danh muc (Phan F) — kien truc mo rong duoc, xem
              `DANH_MUC` o dau tep. */}
          <select
            className="select select-mini"
            aria-label="Tìm trong danh mục"
            value={danhMuc}
            onChange={(e) => setDanhMuc(e.target.value as DanhMuc)}
          >
            {DANH_MUC.map((m) => (
              <option key={m.khoa} value={m.khoa} disabled={!m.sanSang}>
                {m.nhan}
                {m.sanSang ? "" : " (sắp có)"}
              </option>
            ))}
          </select>
          <input
            ref={oNhap}
            className="tim-o"
            type="search"
            placeholder="Tìm truyện, tác giả, fandom…"
            aria-label="Tìm truyện, tác giả, fandom"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setChon(-1);
            }}
            enterKeyHint="search"
            role="combobox"
            aria-expanded={danh.length > 0}
            aria-controls={`${idGoc}-ds`}
            aria-activedescendant={
              chon >= 0 && danh.length ? `${idGoc}-kq-${chon}` : undefined
            }
            aria-autocomplete="list"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="button" className="btn btn-sm btn-ghost" onClick={onDong}>
            Đóng
          </button>
        </div>

        <div className="tim-than" id={`${idGoc}-ds`} role="listbox">
          {trangThai === "dau" ? (
            <div className="tim-dau-goi-y">
              <p className="tim-trong">
                Gõ tên <strong>truyện</strong>, <strong>tác giả</strong>, <strong>fandom</strong> hoặc{" "}
                <strong>người dùng</strong>.
              </p>
              {fandomPhoBien.length ? (
                <div className="tim-fandom-nhanh" aria-label="Fandom có truyện">
                  <span className="tim-fandom-nhan">Fandom</span>
                  {fandomPhoBien.map((f) => (
                    <Link
                      key={f.ten}
                      className="tim-fandom-chip"
                      href={`/library?fandom=${encodeURIComponent(f.ten)}`}
                      onClick={onDong}
                    >
                      {f.ten}
                      <span className="tim-fandom-so">{f.so}</span>
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>
          ) : trangThai === "dang-tai" ? (
            <p className="tim-trong" role="status">
              Đang tìm “{tu}”…
            </p>
          ) : trangThai === "loi" ? (
            <p className="tim-trong" role="alert">
              Không tìm được lúc này. Thử lại sau một chút.
            </p>
          ) : trangThai === "rong" ? (
            <div className="tim-trong" role="status">
              <p>Không có kết quả cho “{tu}”.</p>
              <p className="hint">
                Thử tên ngắn hơn, bỏ dấu, hoặc tìm theo fandom — ví dụ “Naruto”, “One Piece”.
              </p>
            </div>
          ) : (
            <>
              {fandomGoiY.length || tacGiaGoiY.length ? (
                <section aria-labelledby={`${idGoc}-goiy`}>
                  <h2 className="tim-nhom" id={`${idGoc}-goiy`}>
                    <IconTag size={15} /> Gợi ý
                  </h2>
                  {fandomGoiY.map((f, i) => (
                    <Link
                      key={`f-${f.ten}`}
                      id={`${idGoc}-kq-${i}`}
                      role="option"
                      aria-selected={chon === i}
                      className={`tim-kq tim-kq-goiy${chon === i ? " la-chon" : ""}`}
                      href={`/library?fandom=${encodeURIComponent(f.ten)}`}
                      onClick={onDong}
                      onMouseEnter={() => setChon(i)}
                    >
                      <span className="tim-goiy-icon" aria-hidden="true">
                        <IconTag size={16} />
                      </span>
                      <span className="tim-chu">
                        <strong>{f.ten}</strong>
                        <span className="hint">Fandom · {f.so} truyện</span>
                      </span>
                    </Link>
                  ))}
                  {tacGiaGoiY.map((a, i) => {
                    const vt = bd.tacgia + i;
                    return (
                      <Link
                        key={`a-${a.ten}`}
                        id={`${idGoc}-kq-${vt}`}
                        role="option"
                        aria-selected={chon === vt}
                        className={`tim-kq tim-kq-goiy${chon === vt ? " la-chon" : ""}`}
                        href={`/library?q=${encodeURIComponent(a.ten)}`}
                        onClick={onDong}
                        onMouseEnter={() => setChon(vt)}
                      >
                        <span className="tim-goiy-icon" aria-hidden="true">
                          <IconFeather size={16} />
                        </span>
                        <span className="tim-chu">
                          <strong>{a.ten}</strong>
                          <span className="hint">Tác giả · {a.so} truyện</span>
                        </span>
                      </Link>
                    );
                  })}
                </section>
              ) : null}

              {truyen.length ? (
                <section aria-labelledby={`${idGoc}-truyen`}>
                  <h2 className="tim-nhom" id={`${idGoc}-truyen`}>
                    <IconBook size={15} /> Truyện
                  </h2>
                  {truyen.map((n, i) => {
                    const vt = bd.truyen + i;
                    const tacGia = n.external_author_name?.trim();
                    // Tac gia truoc (nguoi doc hay nho ten nguoi viet), roi hai the.
                    const phu: string[] = [];
                    if (tacGia && !/^unknown/i.test(tacGia)) phu.push(tacGia);
                    phu.push(...theChoThe(n, 2, [fandomCauTruc(n)]));
                    return (
                      <Link
                        key={n.novel_id}
                        id={`${idGoc}-kq-${vt}`}
                        role="option"
                        aria-selected={chon === vt}
                        className={`tim-kq${chon === vt ? " la-chon" : ""}`}
                        href={`/novels/${n.novel_id}`}
                        onClick={onDong}
                        onMouseEnter={() => setChon(vt)}
                      >
                        <span className="tim-bia">
                          <NovelCover
                            novelId={n.novel_id}
                            title={n.title}
                            coverUrl={n.cover_url}
                            size="thumb"
                          />
                        </span>
                        <span className="tim-chu">
                          <strong>{n.title}</strong>
                          {phu.length > 0 ? <span className="hint">{phu.join(" · ")}</span> : null}
                        </span>
                      </Link>
                    );
                  })}
                </section>
              ) : null}

              {audio.length ? (
                <section aria-labelledby={`${idGoc}-audio`}>
                  <h2 className="tim-nhom" id={`${idGoc}-audio`}>
                    <IconHeadphones size={15} /> Audio
                  </h2>
                  {audio.map((n, i) => {
                    const vt = bd.audio + i;
                    return (
                      <Link
                        key={n.novel_id}
                        id={`${idGoc}-kq-${vt}`}
                        role="option"
                        aria-selected={chon === vt}
                        className={`tim-kq${chon === vt ? " la-chon" : ""}`}
                        href={`/novels/${n.novel_id}`}
                        onClick={onDong}
                        onMouseEnter={() => setChon(vt)}
                      >
                        <span className="tim-bia">
                          <NovelCover
                            novelId={n.novel_id}
                            title={n.title}
                            coverUrl={n.cover_url}
                            size="thumb"
                          />
                        </span>
                        <span className="tim-chu">
                          <strong>{n.title}</strong>
                          <span className="hint">
                            {n.audio_chapter_count} chương có audio
                          </span>
                        </span>
                      </Link>
                    );
                  })}
                </section>
              ) : null}

              {animation.length ? (
                <section aria-labelledby={`${idGoc}-animation`}>
                  <h2 className="tim-nhom" id={`${idGoc}-animation`}>
                    <IconFilm size={15} /> Animation
                  </h2>
                  {animation.map((s, i) => {
                    const vt = bd.animation + i;
                    return (
                      <Link
                        key={s.series_id}
                        id={`${idGoc}-kq-${vt}`}
                        role="option"
                        aria-selected={chon === vt}
                        className={`tim-kq${chon === vt ? " la-chon" : ""}`}
                        href={`/animation/${s.series_id}`}
                        onClick={onDong}
                        onMouseEnter={() => setChon(vt)}
                      >
                        <span className="tim-bia">
                          <NovelCover
                            novelId={s.series_id}
                            title={s.title}
                            coverUrl={s.cover_url}
                            size="thumb"
                          />
                        </span>
                        <span className="tim-chu">
                          <strong>{s.title}</strong>
                          {getReaderTags(s, 3).length > 0 ? (
                            <span className="hint">{getReaderTags(s, 3).join(" · ")}</span>
                          ) : null}
                        </span>
                      </Link>
                    );
                  })}
                </section>
              ) : null}

              {nguoi.length ? (
                <section aria-labelledby={`${idGoc}-nguoi`}>
                  <h2 className="tim-nhom" id={`${idGoc}-nguoi`}>
                    <IconUser size={15} /> Người dùng
                  </h2>
                  {nguoi.map((p, i) => {
                    const vt = bd.nguoi + i;
                    return (
                      <Link
                        key={p.user_id}
                        id={`${idGoc}-kq-${vt}`}
                        role="option"
                        aria-selected={chon === vt}
                        className={`tim-kq${chon === vt ? " la-chon" : ""}`}
                        href={`/u/${p.username}`}
                        onClick={onDong}
                        onMouseEnter={() => setChon(vt)}
                      >
                        <Avatar
                          name={p.display_name || p.username}
                          avatarUrl={p.avatar_url}
                          className="tim-avatar"
                        />
                        <span className="tim-chu">
                          <strong>{p.display_name || p.username}</strong>
                          <span className="hint mono">@{p.username}</span>
                        </span>
                        {/* Huy hieu o cuoi hang: chung la thong tin PHU, va dat
                            truoc ten thi mat doc chung truoc ca nguoi. */}
                        <span className="tim-hh">
                          {p.is_author ? <AuthorBadge size="sm" /> : null}
                          {p.is_author && p.rank ? (
                            <RankBadge rank={p.rank} size="sm" />
                          ) : null}
                        </span>
                      </Link>
                    );
                  })}
                </section>
              ) : null}

              {/*
                Muc PHU — dung ba ket qua, dung sau cung. Truyen va nguoi van
                la uu tien cua hop tim nay; bai dang chi la duong tat cho ai
                nho mot cau ai do vua viet.
              */}
              {bai.length ? (
                <section aria-labelledby={`${idGoc}-bai`}>
                  <h2 className="tim-nhom" id={`${idGoc}-bai`}>
                    <IconMegaphone size={15} /> Bài viết
                  </h2>
                  {bai.map((b, i) => {
                    const vt = bd.bai + i;
                    return (
                      <Link
                        key={b.post_id}
                        id={`${idGoc}-kq-${vt}`}
                        role="option"
                        aria-selected={chon === vt}
                        className={`tim-kq${chon === vt ? " la-chon" : ""}`}
                        href={`/posts/${b.post_id}`}
                        onClick={onDong}
                        onMouseEnter={() => setChon(vt)}
                      >
                        <Avatar
                          name={b.author?.display_name || "?"}
                          avatarUrl={b.author?.avatar_url}
                          className="tim-avatar"
                        />
                        <span className="tim-chu">
                          <strong>
                            {b.text.length > 70 ? `${b.text.slice(0, 70)}…` : b.text}
                          </strong>
                          <span className="hint">
                            {b.author?.display_name || b.author?.username || ""}
                          </span>
                        </span>
                      </Link>
                    );
                  })}
                </section>
              ) : null}
            </>
          )}
        </div>

        {tu ? (
          <div className="tim-chan">
            {/* Thu vien la trang ket qua day du (loc, sap xep, URL giu trang
                thai). Enter khi chua chon muc nao cung dua toi day. */}
            <Link
              className="btn btn-sm"
              href={`/library?q=${encodeURIComponent(tu)}`}
              onClick={onDong}
            >
              <IconSearch size={14} /> Xem tất cả kết quả “{tu}” trong Thư viện
            </Link>
            <span className="tim-meo hint" aria-hidden="true">
              <kbd>↑</kbd>
              <kbd>↓</kbd> chọn · <kbd>Enter</kbd> mở · <kbd>Esc</kbd> đóng
            </span>
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
