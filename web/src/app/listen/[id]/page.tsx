"use client";

/**
 * Trang NGHE rieng — V4, Phan 2A-2M (overnight Phase 2).
 *
 * TACH khoi trang doc (`/chapters/[id]`): truoc day mot chuong co audio thi
 * `ChapterPlayer` + `MiniPlayer` + `ListenReporter` deu nam TREN dau trang
 * doc, chiem het man hinh dau tien truoc ca noi dung. Gio trang doc CHI con
 * chu (xem ghi chu o do); moi thu lien quan toi NGHE — trinh phat, chuong
 * truoc/sau, chon tap, phu de dong bo, binh luan kem moc — chuyen sang day.
 *
 * MOT request rieng cho danh sach chuong (`api.getNovel`), KHONG phai N+1:
 * dung 2 request tong cong (chuong hien tai + danh sach chuong cua truyen)
 * bat ke truyen co bao nhieu chuong — xem ghi chu o `load()`.
 *
 * KHONG tu phat khi dieu huong — `AudioEngineProvider.phat()` chi TAI audio,
 * khong bao gio tu goi `.play()`.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Chapter, type Novel } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { useAudioEngine } from "@/components/AudioEngine";
import { ChapterPlayer } from "@/components/ChapterPlayer";
import { MiniPlayer } from "@/components/MiniPlayer";
import { ListenReporter } from "@/components/ListenReporter";
import { ContinueListenReporter } from "@/components/ContinueListenReporter";
import { ChapterComments } from "@/components/ChapterComments";
import { SyncedTranscript } from "@/components/SyncedTranscript";
import { EmptyState, ErrorState, SkeletonList, formatNumber } from "@/components/ui";
import { IconBook, IconHeadphones } from "@/components/Icons";

interface ListenData {
  chapter: Chapter;
  novel: Novel;
  chapters: Chapter[];
  coAudio: boolean;
  audioOutdated: boolean;
}

export default function ListenPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();
  const { trangThai: audioTrangThai, dieuKhien: audioDieuKhien } = useAudioEngine();
  const mocPhat = useRef<HTMLDivElement | null>(null);

  const [moBanChu, setMoBanChu] = useState(false);
  const [moChonTap, setMoChonTap] = useState(false);
  const [locTap, setLocTap] = useState("");

  const load = useCallback(async (): Promise<ListenData> => {
    const { chapter, audio, novel: novelBrief, audio_outdated } =
      await api.getChapter(id);
    if (!novelBrief) {
      throw new Error("Chương này chưa gắn với truyện nào.");
    }
    // HAI request tong cong, khong phu thuoc so chuong: chuong hien tai
    // (o tren) + danh sach chuong cua truyen (o day) — KHONG goi lai
    // `getNovel` cho tung chuong khi nguoi dung nhay tap trong CUNG truyen,
    // vi ca trang nay re-mount (route doi) nen effect chay lai dung MOT lan.
    const { novel, chapters } = await api.getNovel(novelBrief.novel_id);
    return {
      chapter,
      novel,
      // KHONG tu sap xep theo `order_index`: truong do CHI co y nghia sau
      // khi tac gia da tung dung tinh nang "sap xep lai" — chuong tao binh
      // thuong deu mang gia tri MAC DINH giong het nhau, va sap theo do se
      // tron hang. `GET /api/novels/{id}` da tra ve DUNG thu tu hien thi
      // (`/novels/[id]/page.tsx` cung dung thang mang nay, khong sap lai).
      chapters,
      // `chapter.has_audio` CHI co trong danh sach chuong cua `getNovel`
      // (stamp rieng cho trang chi tiet truyen) — KHONG co trong chinh
      // `chapter` cua `getChapter()`. Phai dung `audio` (AudioTrack | null)
      // cua CHINH lan goi nay, khong phai `chapter.has_audio` (luon
      // `undefined` o day, tuc la LUON truthy voi phep so sanh `!== false`).
      coAudio: Boolean(audio),
      audioOutdated: Boolean(audio_outdated),
    };
  }, [id]);

  const { data, loading, error, missing, reload } = useAsyncData(load);

  const chapter = data?.chapter ?? null;
  const isOwner = profile?.user_id === chapter?.owner_id;

  const chiSoHienTai = useMemo(
    () => (data ? data.chapters.findIndex((c) => c.chapter_id === id) : -1),
    [data, id],
  );
  // So thu tu HIEN THI = VI TRI trong mang (giong `/novels/[id]/page.tsx`),
  // KHONG phai `chapter.order_index` — xem ghi chu o `load()`.
  const soThuTu = useMemo(
    () => new Map((data?.chapters ?? []).map((c, i) => [c.chapter_id, i + 1])),
    [data],
  );
  const tapTruoc = data && chiSoHienTai > 0 ? data.chapters[chiSoHienTai - 1] : null;
  const tapSau =
    data && chiSoHienTai >= 0 && chiSoHienTai < data.chapters.length - 1
      ? data.chapters[chiSoHienTai + 1]
      : null;

  const danhSachLoc = useMemo(() => {
    if (!data) return [];
    const tu = locTap.trim().toLowerCase();
    if (!tu) return data.chapters;
    return data.chapters.filter((c) => c.title.toLowerCase().includes(tu));
  }, [data, locTap]);

  /* Bien chuong nay thanh BAI DANG PHAT TOAN CUC — CHI o trang Nghe, khong
     con o trang doc. `phat()` la khong-lam-gi khi day DA la bai dang phat. */
  useEffect(() => {
    if (!chapter || !data?.coAudio) return;
    if (audioTrangThai.chapterId === chapter.chapter_id) return;
    audioDieuKhien.phat(chapter.chapter_id, chapter.title);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter?.chapter_id, data?.coAudio]);

  useEffect(() => {
    if (!profile || !chapter) return;
    api.reportReadProgress(chapter.novel_id, chapter.chapter_id).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.user_id, chapter?.chapter_id]);

  if (loading) {
    return (
      <div className="page">
        <div className="sk sk-title" style={{ height: 30, width: "45%" }} />
        <SkeletonList count={3} />
      </div>
    );
  }

  if (missing || (!loading && !data && !error)) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy chương này"
          action={
            <Link className="btn btn-primary" href="/fanfic">
              Về trang khám phá
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !data || !chapter) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được chương."} onRetry={reload} />
      </div>
    );
  }

  const { novel, audioOutdated, coAudio } = data;

  return (
    <div className="page">
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <Link href={`/novels/${novel.novel_id}`} className="hint crumb">
          ← {novel.title}
        </Link>
      </nav>

      <header className="stack-2 reader-head">
        <span className="eyebrow eyebrow-icon">
          <IconHeadphones size={17} /> Đang nghe
        </span>
        <h1 className="page-title">{chapter.title}</h1>
      </header>

      {/*
        Tap truoc/sau + chon tap LUON hien, bat ke chuong HIEN TAI co audio
        hay khong — nguoi dung con can dieu huong toi mot tap KHAC co audio.
        Chi rieng trinh phat/canh bao/phu de/binh luan moi phu thuoc coAudio.
      */}
      <nav className="row row-spread listen-nav" aria-label="Điều hướng tập">
        {tapTruoc ? (
          <Link className="btn" href={`/listen/${tapTruoc.chapter_id}`}>
            <span aria-hidden="true">←</span> Tập trước
          </Link>
        ) : (
          <span className="btn" aria-disabled="true">
            <span aria-hidden="true">←</span> Tập trước
          </span>
        )}
        <button
          type="button"
          className="btn btn-ghost"
          aria-expanded={moChonTap}
          onClick={() => setMoChonTap((v) => !v)}
        >
          Danh sách tập ({chiSoHienTai + 1}/{data.chapters.length})
        </button>
        {tapSau ? (
          <Link className="btn" href={`/listen/${tapSau.chapter_id}`}>
            Tập sau <span aria-hidden="true">→</span>
          </Link>
        ) : (
          <span className="btn" aria-disabled="true">
            Tập sau <span aria-hidden="true">→</span>
          </span>
        )}
      </nav>

      {moChonTap ? (
        <div className="listen-chon-tap" role="region" aria-label="Chọn tập để nghe">
          {data.chapters.length > 20 ? (
            <input
              className="input"
              type="search"
              placeholder="Tìm tập theo tên…"
              value={locTap}
              onChange={(e) => setLocTap(e.target.value)}
              aria-label="Tìm tập"
            />
          ) : null}
          <div className="listen-chon-tap-list">
            {danhSachLoc.map((c) => {
              const dangXem = c.chapter_id === chapter.chapter_id;
              return (
                <Link
                  key={c.chapter_id}
                  href={`/listen/${c.chapter_id}`}
                  className={`listen-chon-tap-item${dangXem ? " la-chon" : ""}`}
                  aria-current={dangXem ? "true" : undefined}
                  onClick={() => setMoChonTap(false)}
                >
                  <span className="hint mono">{soThuTu.get(c.chapter_id)}.</span>
                  <span className="truncate">{c.title}</span>
                  {!c.has_audio ? (
                    <span className="badge">Chưa có audio</span>
                  ) : null}
                </Link>
              );
            })}
            {danhSachLoc.length === 0 ? (
              <p className="hint">Không có tập nào khớp “{locTap}”.</p>
            ) : null}
          </div>
        </div>
      ) : null}

      {!coAudio ? (
        <EmptyState
          icon="🎧"
          title="Chương này chưa có audio"
          hint={
            isOwner
              ? "Bạn có thể tạo audio cho chương trong khu vực tác giả."
              : "Tác giả chưa tạo bản audio cho chương này."
          }
          action={
            isOwner ? (
              <Link className="btn btn-primary" href="/write">
                Tạo audio cho chương
              </Link>
            ) : (
              <Link className="btn" href={`/chapters/${chapter.chapter_id}`}>
                Đọc chương này
              </Link>
            )
          }
        />
      ) : (
        <>
          {audioOutdated ? (
            <div className="alert alert-warn" role="status">
              <span aria-hidden="true">⚠</span>
              <span className="stack-2">
                <span>
                  Chương này đã được sửa sau khi tạo audio, nên{" "}
                  <strong>audio có thể không còn khớp</strong> với nội dung
                  mới. Bản audio hiện tại vẫn nghe và tải được.
                </span>
                {/* Nut that, khong phai lien ket trong cau (M4): vung bam
                    du to o mobile, va duong dan sang cho tao lai phai RO. */}
                {isOwner ? (
                  <Link className="btn btn-sm" href="/write">
                    Tạo lại audio trong khu vực tác giả
                  </Link>
                ) : null}
              </span>
            </div>
          ) : null}

          <div className="stack listen-col" ref={mocPhat}>
            <ChapterPlayer
              novelId={novel.novel_id}
              novelTitle={novel.title}
              coverUrl={novel.cover_url}
              chapterTitle={chapter.title}
            />
          </div>

          <MiniPlayer moc={mocPhat} />
          <ListenReporter chapterId={chapter.chapter_id} />
          {profile ? (
            <ContinueListenReporter
              novelId={chapter.novel_id}
              chapterId={chapter.chapter_id}
            />
          ) : null}

          <section className="stack-2" aria-label="Phụ đề đồng bộ">
            <h2 className="section-title">Phụ đề</h2>
            <SyncedTranscript chapterId={chapter.chapter_id} />
          </section>
        </>
      )}

      {/* Ban chu GAP mac dinh — trang nay uu tien NGHE, khong phai doc.
          Luon hien du co audio hay khong: van la chu cua chuong. */}
      <section className="stack-2">
        <button
          type="button"
          className="btn btn-sm"
          aria-expanded={moBanChu}
          onClick={() => setMoBanChu((v) => !v)}
        >
          <span aria-hidden="true">{moBanChu ? "✕" : "📖"}</span>{" "}
          {moBanChu ? "Đóng bản chữ" : "Mở bản chữ"}
        </button>
        {moBanChu ? (
          <section className="reader listen-ban-chu" aria-label="Nội dung chương">
            <span className="hint eyebrow-icon">
              <IconBook size={15} /> {formatNumber(chapter.char_count)} ký tự
            </span>
            {chapter.content ? (
              <div className="prose">{chapter.content}</div>
            ) : (
              <p className="hint">Chương này chưa có nội dung.</p>
            )}
          </section>
        ) : null}
      </section>

      <div className="listen-col">
        <ChapterComments chapterId={chapter.chapter_id} />
      </div>
    </div>
  );
}
