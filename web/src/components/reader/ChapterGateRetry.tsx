"use client";

/**
 * THU LAI CHUONG BI GATE KHI MAY CHU TRA 403 (fix login-gate).
 *
 * NGUYEN NHAN: trang chuong la Server Component, token chi nam o
 * localStorage nen request may chu khong kem `Authorization` — backend
 * tuong nguoi xem la khach va tra 403 cho tap bi gate, ngay ca khi user
 * DA dang nhap. Chi trinh duyet moi doc duoc token, nen phan thu lai
 * nay PHAI chay o client.
 *
 * HANH VI:
 * - Khoi tao = dung EmptyState ma server da ve (theo `gateKind`). Khach
 *   khong co token thi effect khong lam gi them: khong request nao, khong
 *   nhap nhay, hanh vi khach giu nguyen 100%.
 * - Co token thi chuyen sang "dang tai" roi goi `api.getChapter` (tu dong
 *   kem Bearer tu localStorage). Thanh cong thi ve dung noi dung chuong;
 *   van 403 thi ve EmptyState theo loai gate cua loi (login/premium);
 *   loi khac thi ve ErrorState.
 * - KHONG dua token len URL, KHONG luu token moi o dau — dung nguyen co
 *   che Bearer localStorage cua `lib/api`.
 * - Khong lo noi dung cho khach: chuong chi duoc fetch khi co token, va
 *   backend van la nguoi quyet dinh 403 theo tier/chu quyen.
 *
 * PHAN NOI DUNG la BAN SAO cua render thanh cong o
 * `app/chapters/[id]/page.tsx` (cung ChapterInteractiveReader,
 * ChapterExperience, Hoi AI, binh luan, dieu huong truoc/sau). Sua trang
 * chuong thi dong bo ca hai cho.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  getToken,
  type AudioTrack,
  type Chapter,
  type NovelBrief,
} from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import { IconBook, IconHeadphones, IconList } from "@/components/Icons";
import { tachDoanVan } from "@/lib/chapterSync";
import { cheDoKhiMo, type TuyChonCheDo } from "@/lib/readerSession";
import {
  ChapterInteractiveReader,
  ChapterOwnerAudioAction,
} from "@/components/ChapterInteractiveReader";
import { ChapterExperience } from "@/components/reader/ChapterExperience";
import { ChapterNavLink, type ChuongLienKe } from "@/components/reader/ChapterNavLink";
import { ChapterComments } from "@/components/ChapterComments";
import { AskAiPanel } from "@/components/AskAiPanel";
import { AskAiAssistantStoryEntry } from "@/components/ai/AskAiAssistantStoryEntry";

/** Gioi han cho danh sach chuong (nut truoc/sau) — giong ban may chu. */
const CHO_DS_CHUONG_MS = 6000;

type TrangThai =
  | { kieu: "dang-tai" }
  | {
      kieu: "noi-dung";
      chapter: Chapter;
      audio: AudioTrack | null;
      novel: NovelBrief | null;
      audioOutdated: boolean;
      dsChuong: Chapter[];
    }
  | { kieu: "can-dang-nhap" }
  | { kieu: "can-premium" }
  | { kieu: "loi"; message: string };

function biKhoa(kind: "login" | "premium"): TrangThai {
  return kind === "premium" ? { kieu: "can-premium" } : { kieu: "can-dang-nhap" };
}

function lienKe(c: Chapter | null): ChuongLienKe | null {
  return c ? { chapter_id: c.chapter_id, title: c.title, has_audio: c.has_audio } : null;
}

export function ChapterGateRetry({
  chapterId,
  gateKind,
  mode,
  autoplay,
  resume,
  prefs,
}: {
  chapterId: string;
  /** Loai gate ma may chu gap — de hien dung EmptyState khi khach / van 403. */
  gateKind: "login" | "premium";
  /** Tham so URL truyen xuong tu trang may chu (mode/autoplay/resume). */
  mode?: string;
  autoplay?: string;
  resume?: string;
  /** Tuy chon doc giai ma tu cookie o may chu (giong ban thanh cong). */
  prefs: TuyChonCheDo;
}) {
  // Khoi tao = EmptyState cua server: khach khong thay gi doi, khong flash.
  const [trangThai, setTrangThai] = useState<TrangThai>(() => biKhoa(gateKind));
  // Doi chuong (hoac doi loai gate) thi xoa noi dung cu TRONG LUC RENDER
  // (mau React khuyen dung cho "reset state khi prop doi") — khong hien
  // chuong cu trong luc cho chuong moi (vua lac vua lo noi dung sai chuong).
  const khoaHienTai = `${chapterId}:${gateKind}`;
  const [khoaTruoc, setKhoaTruoc] = useState(khoaHienTai);
  if (khoaTruoc !== khoaHienTai) {
    setKhoaTruoc(khoaHienTai);
    setTrangThai(biKhoa(gateKind));
  }

  useEffect(() => {
    if (!getToken()) return;
    let huy = false;
    // Chuyen sang "dang tai" ngay khi bat dau fetch co token, de user da
    // dang nhap khong ngoi tren man hinh "can dang nhap" sai trong luc cho.
    // Effect khong phu thuoc trangThai nen khong lap lai hay cascade: chay
    // 1 lan moi chapterId/gateKind, cac setState sau do deu nam trong
    // callback async.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- ly do nhu tren
    setTrangThai({ kieu: "dang-tai" });
    api
      .getChapter(chapterId)
      .then(async (ket_qua) => {
        if (huy) return;
        // Danh sach chuong cho nut truoc/sau: best-effort nhu ban may chu
        // (hong hoac cham thi chi mat hai nut, chu van hien).
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
        if (huy) return;
        setTrangThai({
          kieu: "noi-dung",
          chapter: ket_qua.chapter,
          audio: ket_qua.audio,
          novel: ket_qua.novel ?? null,
          audioOutdated: Boolean(ket_qua.audio_outdated),
          dsChuong,
        });
      })
      .catch((err) => {
        if (huy) return;
        if (err instanceof ApiError && err.status === 403) {
          // Backend tra 403 voi detail chua "Premium" cho tap khoa premium,
          // "dang nhap" cho tap khoa login — tach de hien dung nut CTA,
          // giong cach trang may chu tach.
          setTrangThai(err.message.includes("Premium") ? { kieu: "can-premium" } : { kieu: "can-dang-nhap" });
        } else {
          setTrangThai({ kieu: "loi", message: errorMessage(err) });
        }
      });
    return () => {
      huy = true;
    };
  }, [chapterId, gateKind]);

  if (trangThai.kieu === "dang-tai") {
    return (
      <div className="page">
        <Loading label="Đang tải chương…" />
      </div>
    );
  }

  if (trangThai.kieu === "can-dang-nhap") {
    return (
      <div className="page">
        <EmptyState
          icon="🔒"
          title="Tập này cần đăng nhập"
          action={
            <Link className="btn btn-primary" href="/login" prefetch={false}>
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  if (trangThai.kieu === "can-premium") {
    return (
      <div className="page">
        <EmptyState
          icon="⭐"
          title="Tập này cần Premium"
          action={
            <Link className="btn btn-primary" href="/premium" prefetch={false}>
              Xem gói Premium
            </Link>
          }
        />
      </div>
    );
  }

  if (trangThai.kieu === "loi") {
    return (
      <div className="page">
        <ErrorState message={trangThai.message} />
      </div>
    );
  }

  const { chapter, audio, novel, audioOutdated, dsChuong } = trangThai;
  const doanVan = tachDoanVan(chapter.content);
  const coAudio = Boolean(audio);

  const ds = dsChuong ?? [];
  const i = ds.findIndex((c) => c.chapter_id === chapterId);
  const chuongTruoc = i > 0 ? ds[i - 1] : null;
  const chuongSau = i >= 0 && i < ds.length - 1 ? ds[i + 1] : null;
  const soThuTu = i >= 0 ? i + 1 : 0;
  const tongSo = ds.length;

  const initialMode = cheDoKhiMo({
    tuUrl: mode,
    daLuu: prefs.cheDo,
    coAudio,
    coChu: doanVan.length > 0,
  });
  const urlRequestsPlay = autoplay === "1" || autoplay === "true";
  const autoResume = resume === "1";

  return (
    <ChapterInteractiveReader novelId={chapter.novel_id} chapterId={chapter.chapter_id}>
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <Link href={`/novels/${chapter.novel_id}`} className="hint crumb">
          ← {novel?.title ?? "Về truyện"}
        </Link>
      </nav>

      <header className="stack-2 reader-head">
        <h1 className="page-title">{chapter.title}</h1>
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
        audioOutdated={audioOutdated}
        initialMode={initialMode}
        initialPrefs={prefs}
        urlRequestsPlay={urlRequestsPlay}
        autoResume={autoResume}
        prev={lienKe(chuongTruoc)}
        next={lienKe(chuongSau)}
        ownerId={chapter.owner_id}
      >
        <AskAiPanel
          novelId={chapter.novel_id}
          chapterId={chapter.chapter_id}
          chapterIndex={chapter.order_index}
          chapterContent={chapter.content}
        />
        <AskAiAssistantStoryEntry
          novelId={chapter.novel_id}
          chapterId={chapter.chapter_id}
          chapterIndex={chapter.order_index}
        />

        <div className="listen-col">
          <ChapterComments chapterId={chapter.chapter_id} />
        </div>

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
              <span className="reader-nav-prev" aria-hidden="true" />
            )}

            <Link className="btn btn-ghost reader-nav-up" href={`/novels/${novel.novel_id}`}>
              <span aria-hidden="true">☰</span> Danh sách chương
              {tongSo > 0 ? <span className="hint reader-nav-count">{soThuTu}/{tongSo}</span> : null}
            </Link>

            {chuongSau ? (
              <ChapterNavLink
                target={lienKe(chuongSau)!}
                className="btn reader-nav-next"
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
              <span className="hint reader-nav-next reader-nav-end">Hết chương hiện có</span>
            )}
          </nav>
        ) : null}
      </ChapterExperience>
    </ChapterInteractiveReader>
  );
}
