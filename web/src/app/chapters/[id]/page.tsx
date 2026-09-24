/**
 * Trang CHUONG — doc VA nghe tren mot duong dan chinh tac (sprint UX doc/nghe,
 * 2026-09-24). Truoc day doc o day, nghe o `/listen/[id]` (overnight Phase 2A);
 * `/listen/[id]` gio chuyen huong ve day voi `?mode=listen`.
 *
 * Server Component: van ban chuong van ve o MAY CHU (SEO, `Ctrl+F`, trinh doc
 * man hinh), metadata/canonical/OpenGraph giu nguyen. Phan tuong tac (che do,
 * trinh phat, to sang doan dang doc, tiep tuc doc/nghe) nam o
 * `components/reader/ChapterExperience.tsx`, dung CHUNG dong co audio toan cuc.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { API_BASE, api, ApiError, type AudioTrack, type Chapter, type NovelBrief } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { ChapterComments } from "@/components/ChapterComments";
import { AskAiPanel } from "@/components/AskAiPanel";
import {
  ChapterInteractiveReader,
  ChapterOwnerAudioAction,
} from "@/components/ChapterInteractiveReader";
import { ChapterExperience } from "@/components/reader/ChapterExperience";
import { ChapterNavLink, type ChuongLienKe } from "@/components/reader/ChapterNavLink";
import { EmptyState, ErrorState } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import { IconBook, IconHeadphones, IconList } from "@/components/Icons";
import { tachDoanVan } from "@/lib/chapterSync";
import { cheDoKhiMo, COOKIE_CHE_DO, giaiMaCookie } from "@/lib/readerSession";

/**
 * Dynamic metadata cho SEO, OpenGraph (article), Twitter card va canonical URL.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const res = await fetch(`${API_BASE}/api/chapters/${encodeURIComponent(id)}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) throw new Error("not found");
    const data = await res.json();
    const chapter: Chapter = data.chapter;
    const novel: NovelBrief | null = data.novel ?? null;
    const title = novel
      ? `${chapter.title} - ${novel.title} | Fanfic World`
      : `${chapter.title} | Fanfic World`;
    const excerpt = chapter.content
      ? chapter.content.slice(0, 160).replace(/\s+/g, " ").trim()
      : `Đọc chương ${chapter.title} tại Fanfic World.`;
    const canonical = `https://fanfic.world/chapters/${chapter.chapter_id}`;
    const images = novel?.cover_url ? [novel.cover_url] : [];

    return {
      title,
      description: excerpt,
      alternates: { canonical },
      openGraph: {
        title,
        description: excerpt,
        url: canonical,
        siteName: "Fanfic World",
        type: "article",
        images,
      },
      twitter: {
        card: "summary",
        title,
        description: excerpt,
        images,
      },
    };
  } catch {
    return {
      title: "Đọc chương | Fanfic World",
      description: "Đọc chương fanfic tiếng Việt tại Fanfic World.",
    };
  }
}

/** Cho danh sach chuong (chi de dung nut truoc/sau) toi da bay nhieu. */
const CHO_DS_CHUONG_MS = 6000;

function lienKe(c: Chapter | null): ChuongLienKe | null {
  return c ? { chapter_id: c.chapter_id, title: c.title, has_audio: c.has_audio } : null;
}

export default async function ChapterPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ mode?: string; autoplay?: string }>;
}) {
  const { id } = await params;
  const sp = searchParams ? await searchParams : {};

  let ket_qua: {
    chapter: Chapter;
    audio: AudioTrack | null;
    novel?: NovelBrief | null;
    audio_outdated?: boolean;
  } | null = null;
  let missing = false;
  let errorMsg = "";

  try {
    ket_qua = await api.getChapter(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      missing = true;
    } else {
      errorMsg = errorMessage(err);
    }
  }

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy chương này"
          action={
            <Link className="btn btn-primary" href="/fanfic" prefetch={false}>
              Về trang khám phá
            </Link>
          }
        />
      </div>
    );
  }

  if (errorMsg || !ket_qua || !ket_qua.chapter) {
    return (
      <div className="page">
        <ErrorState message={errorMsg || "Không tải được chương."} />
      </div>
    );
  }

  const chapter: Chapter = ket_qua.chapter;
  const audio: AudioTrack | null = ket_qua.audio;
  const novel: NovelBrief | null = ket_qua.novel ?? null;

  /*
    HAI request, khong phu thuoc so chuong: chuong hien tai (`getChapter`, da
    kem san `novel` nen khong phai goi them chi de lay ten truyen) + danh sach
    chuong cua truyen, de biet chuong TRUOC va chuong SAU la gi (kem
    `has_audio`, de "Chương sau" biet co phat tiep duoc khong).

    Danh sach chuong lay theo kieu KHONG DUOC PHEP LAM HONG VIEC DOC: neu
    `getNovel` that bai thi `dsChuong` chi la rong, mat hai cai nut dieu huong,
    va chu van hien ra binh thuong.

    "That bai" gom ca CHAM: do that 2026-09-24, `GET /api/novels/{id}` cua
    truyen 99 chuong mat 180 giay+ trong mot dot may chu xuong cap, trong khi
    `getChapter` van ~2 giay — trang chuong dung trang trang ca phut chi vi
    hai cai nut. Cho toi da CHO_DS_CHUONG_MS; qua han thi doc chu truoc.
  */
  const novelId = ket_qua.novel?.novel_id ?? ket_qua.chapter?.novel_id;
  const dsChuong: Chapter[] = novelId
    ? await Promise.race([
        api
          .getNovel(novelId)
          .then((r) => r.chapters)
          .catch(() => [] as Chapter[]),
        new Promise<Chapter[]>((xong) => setTimeout(() => xong([]), CHO_DS_CHUONG_MS)),
      ])
    : [];

  const ds = dsChuong ?? [];
  const i = ds.findIndex((c) => c.chapter_id === id);
  const { chuongTruoc, chuongSau, soThuTu, tongSo } = {
    chuongTruoc: i > 0 ? ds[i - 1] : null,
    chuongSau: i >= 0 && i < ds.length - 1 ? ds[i + 1] : null,
    soThuTu: i >= 0 ? i + 1 : 0,
    tongSo: ds.length,
  };

  /*
    Chia doan MOT lan o may chu bang CHINH ham ma bo dong bo dung de dem doan
    (`lib/chapterSync.tachDoanVan`) — lech nhau mot doan la vach sang nhay sai.
  */
  const doanVan = tachDoanVan(chapter.content);
  const coAudio = Boolean(audio);

  /*
    Che do va khung chu can biet NGAY lan ve dau (co trinh phat lon hay khong,
    co hien chu hay khong) — nen doc tu cookie o may chu, khong doi JS. Xem
    `lib/readerSession.ts`. Trang nay von da dong (doc `searchParams`), doc
    cookie khong doi cach cache.
  */
  const kho = await cookies();
  const prefs = giaiMaCookie(kho.get(COOKIE_CHE_DO)?.value);
  const initialMode = cheDoKhiMo({
    tuUrl: sp.mode,
    daLuu: prefs.cheDo,
    coAudio,
    coChu: doanVan.length > 0,
  });
  const urlRequestsPlay = sp.autoplay === "1" || sp.autoplay === "true";

  return (
    <ChapterInteractiveReader
      novelId={chapter.novel_id}
      chapterId={chapter.chapter_id}
    >
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <Link href={`/novels/${chapter.novel_id}`} className="hint crumb">
          ← {novel?.title ?? "Về truyện"}
        </Link>
      </nav>

      <header className="stack-2 reader-head">
        <h1 className="page-title">{chapter.title}</h1>
        {/* Hai nhan RIENG (khong gop chung mot hop flex): tren dien thoai
            "Có bản nghe" gop chung thi bi bop, xuong dong tung chu. */}
        <div className="row row-spread reader-head-meta">
          <span className="hint eyebrow-icon">
            <IconBook size={16} />
            {formatNumber(chapter.char_count)} ký tự
            {novel ? ` · ${novel.title}` : ""}
          </span>
          {coAudio ? (
            <span className="hint eyebrow-icon reader-head-audio">
              <IconHeadphones size={15} /> Có bản nghe
            </span>
          ) : (
            <ChapterOwnerAudioAction ownerId={chapter.owner_id} />
          )}
        </div>
        {novel && tongSo > 0 ? (
          <nav className="reader-topnav" aria-label="Chuyển chương nhanh">
            {chuongTruoc ? (
              <ChapterNavLink
                target={lienKe(chuongTruoc)!}
                href={`/chapters/${chuongTruoc.chapter_id}`}
                className="btn btn-sm btn-ghost"
              >
                <span aria-hidden="true">←</span> Chương trước
              </ChapterNavLink>
            ) : (
              <span className="btn btn-sm btn-ghost" aria-disabled="true">
                <span aria-hidden="true">←</span> Chương trước
              </span>
            )}
            <Link className="btn btn-sm btn-ghost" href={`/novels/${novel.novel_id}`}>
              <IconList size={15} /> {soThuTu}/{tongSo}
            </Link>
            {chuongSau ? (
              <ChapterNavLink
                target={lienKe(chuongSau)!}
                href={`/chapters/${chuongSau.chapter_id}`}
                className="btn btn-sm btn-ghost"
              >
                Chương sau <span aria-hidden="true">→</span>
              </ChapterNavLink>
            ) : (
              <span className="btn btn-sm btn-ghost" aria-disabled="true">
                Chương sau <span aria-hidden="true">→</span>
              </span>
            )}
          </nav>
        ) : null}
      </header>

      <ChapterExperience
        chapterId={chapter.chapter_id}
        chapterTitle={chapter.title}
        novelId={chapter.novel_id}
        novelTitle={novel?.title ?? ""}
        coverUrl={novel?.cover_url}
        paragraphs={doanVan}
        hasAudio={coAudio}
        audioOutdated={Boolean(ket_qua.audio_outdated)}
        initialMode={initialMode}
        initialPrefs={prefs}
        urlRequestsPlay={urlRequestsPlay}
        prev={lienKe(chuongTruoc)}
        next={lienKe(chuongSau)}
        ownerId={chapter.owner_id}
      >
        {/* Hỏi AI — trợ lý hỏi đáp về truyện/chương (xem AskAiPanel.tsx). */}
        <AskAiPanel
          novelId={chapter.novel_id}
          chapterId={chapter.chapter_id}
          chapterIndex={chapter.order_index}
          chapterContent={chapter.content}
        />

        {/* Binh luan chuong — luon hien du co audio hay khong: day la binh
            luan ve NOI DUNG chuong, khong phai chi rieng ban audio. */}
        <div className="listen-col">
          <ChapterComments chapterId={chapter.chapter_id} />
        </div>

        {/*
          Loi ra o CUOI trang. Nam TRONG `ChapterExperience` de hai lien ket
          biet "ban dang nghe" — bam "Chương sau" luc dang phat thi chuong sau
          phat tiep (xem `ChapterNavLink`).
        */}
        {novel ? (
          <nav className="reader-foot reader-nav" aria-label="Điều hướng chương">
            {chuongTruoc ? (
              <ChapterNavLink
                target={lienKe(chuongTruoc)!}
                className="btn reader-nav-prev"
                href={`/chapters/${chuongTruoc.chapter_id}`}
                rel="prev"
              >
                <span aria-hidden="true">←</span>
                <span className="reader-nav-label">
                  <span className="reader-nav-cap">Chương trước</span>
                  <span className="truncate reader-nav-title">{chuongTruoc.title}</span>
                </span>
              </ChapterNavLink>
            ) : (
              /* Giu o trong de nut "sau" khong nhay sang trai o chuong dau. */
              <span className="reader-nav-prev" aria-hidden="true" />
            )}

            <Link className="btn btn-ghost reader-nav-up" href={`/novels/${novel.novel_id}`}>
              <span aria-hidden="true">☰</span> Danh sách chương
              {tongSo > 0 ? (
                <span className="hint reader-nav-count">
                  {soThuTu}/{tongSo}
                </span>
              ) : null}
            </Link>

            {chuongSau ? (
              <ChapterNavLink
                target={lienKe(chuongSau)!}
                className="btn btn-primary reader-nav-next"
                href={`/chapters/${chuongSau.chapter_id}`}
                rel="next"
              >
                <span className="reader-nav-label">
                  <span className="reader-nav-cap">Chương sau</span>
                  <span className="truncate reader-nav-title">{chuongSau.title}</span>
                </span>
                <span aria-hidden="true">→</span>
              </ChapterNavLink>
            ) : (
              /* Het truyen: noi ro thay vi de mot cho trong khong giai thich. */
              <span className="hint reader-nav-next reader-nav-end">
                Hết chương hiện có
              </span>
            )}
          </nav>
        ) : null}
      </ChapterExperience>
    </ChapterInteractiveReader>
  );
}
