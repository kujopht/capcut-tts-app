/**
 * Doc chuong — CHI CHU, chu-truoc-tien (Phan 2A/2E, overnight Phase 2).
 * Server Component SSR van ban, semantic article markup va dynamic metadata cho SEO.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { API_BASE, api, ApiError, type AudioTrack, type Chapter, type NovelBrief } from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { ChapterComments } from "@/components/ChapterComments";
import { AskAiPanel } from "@/components/AskAiPanel";
import {
  ChapterInteractiveReader,
  ChapterOwnerAudioAction,
  ChapterReaderPrefsControl,
} from "@/components/ChapterInteractiveReader";
import { EmptyState, ErrorState, formatNumber } from "@/components/ui";
import { IconBook, IconHeadphones } from "@/components/Icons";

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

export default async function ChapterPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let ket_qua: {
    chapter: Chapter;
    audio: AudioTrack | null;
    novel?: NovelBrief | null;
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
    chuong cua truyen, de biet chuong TRUOC va chuong SAU la gi.

    Danh sach chuong lay theo kieu KHONG DUOC PHEP LAM HONG VIEC DOC: neu
    `getNovel` that bai thi `dsChuong` chi la rong, mat hai cai nut dieu huong,
    va chu van hien ra binh thuong.
  */
  const novelId = ket_qua.novel?.novel_id ?? ket_qua.chapter?.novel_id;
  const dsChuong: Chapter[] = novelId
    ? await api
        .getNovel(novelId)
        .then((r) => r.chapters)
        .catch(() => [] as Chapter[])
    : [];

  const ds = dsChuong ?? [];
  const i = ds.findIndex((c) => c.chapter_id === id);
  const { chuongTruoc, chuongSau, soThuTu, tongSo } = {
    chuongTruoc: i > 0 ? ds[i - 1] : null,
    chuongSau: i >= 0 && i < ds.length - 1 ? ds[i + 1] : null,
    soThuTu: i >= 0 ? i + 1 : 0,
    tongSo: ds.length,
  };

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
        <span className="hint eyebrow-icon">
          <IconBook size={16} />
          {formatNumber(chapter.char_count)} ký tự
          {novel ? ` · ${novel.title}` : ""}
        </span>
        {/*
          MOT lien ket gon toi trai nghiem NGHE rieng (`/listen/[id]`) — KHONG
          con mo trinh phat/MiniPlayer/ListenReporter ngay tai day (Phan 2A).
          Chua co audio thi chi thay huong dan tao (chu so huu) hoac khong
          hien gi ca (nguoi doc thuong — khong ep ho quan tam toi audio).
        */}
        {audio ? (
          <Link
            className="btn btn-sm"
            href={`/listen/${chapter.chapter_id}`}
          >
            <IconHeadphones size={15} /> Nghe chương này
          </Link>
        ) : (
          <ChapterOwnerAudioAction ownerId={chapter.owner_id} />
        )}
      </header>

      {/*
        Tuy chon doc nam NGAY TREN cot chu, khong giau trong mot menu: nguoi
        can chinh co chu la nguoi dang thay chu kho doc, va bat ho di tim la
        bat sai nguoi.
      */}
      <ChapterReaderPrefsControl />

      {/*
        Cot chu hep hon phan con lai cua trang. Mot dong dai ~68 ky tu la nguong
        mat con lan duoc tu cuoi dong nay sang dau dong sau ma khong lac; ca be
        rong 1180px thi doc mot chuong dai rat met.
      */}
      <section className="reader" aria-label="Nội dung chương">
        {chapter.content ? (
          <div className="prose">
            {chapter.content.split(/\n\n+/).map((para, idx) => (
              <p key={idx} style={{ marginBottom: "1.25em" }}>
                {para}
              </p>
            ))}
          </div>
        ) : audio ? (
          // Cac tac pham nhap tu audio dai tap (13 truyen Fanfic Staging,
          // xem docs/reports/) khong co van ban goc — day la trang thai BINH
          // THUONG cua chung, khong phai loi/thieu du lieu.
          <EmptyState
            icon="🎧"
            title="Chương này chỉ có bản audio"
            hint={`Chưa có bản chữ cho chương này${novel ? ` trong ${novel.title}` : ""}. Nghe trọn tập tại trang Nghe.`}
            action={
              <Link className="btn btn-primary" href={`/listen/${chapter.chapter_id}`}>
                <IconHeadphones size={15} /> Nghe tập này
              </Link>
            }
          />
        ) : (
          <p className="hint">Chương này chưa có nội dung.</p>
        )}
      </section>

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
        Loi ra o CUOI chuong. Nguoi vua doc xong dang o day, khong phai o dau
        trang — bat ho cuon nguoc len de tim duong sang chuong sau la mot viec
        thua.
      */}
      {novel ? (
        <nav className="reader-foot reader-nav" aria-label="Điều hướng chương">
          {chuongTruoc ? (
            <Link
              className="btn reader-nav-prev"
              href={`/chapters/${chuongTruoc.chapter_id}`}
              prefetch={false}
              rel="prev"
            >
              <span aria-hidden="true">←</span>
              <span className="reader-nav-label">
                <span className="reader-nav-cap">Chương trước</span>
                <span className="truncate reader-nav-title">{chuongTruoc.title}</span>
              </span>
            </Link>
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
            <Link
              className="btn btn-primary reader-nav-next"
              href={`/chapters/${chuongSau.chapter_id}`}
              prefetch={false}
              rel="next"
            >
              <span className="reader-nav-label">
                <span className="reader-nav-cap">Chương sau</span>
                <span className="truncate reader-nav-title">{chuongSau.title}</span>
              </span>
              <span aria-hidden="true">→</span>
            </Link>
          ) : (
            /* Het truyen: noi ro thay vi de mot cho trong khong giai thich. */
            <span className="hint reader-nav-next reader-nav-end">
              Hết chương hiện có
            </span>
          )}
        </nav>
      ) : null}
    </ChapterInteractiveReader>
  );
}
