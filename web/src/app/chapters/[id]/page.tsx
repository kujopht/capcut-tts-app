"use client";

/**
 * Doc chuong — CHI CHU, chu-truoc-tien (Phan 2A/2E, overnight Phase 2).
 *
 * TRUOC: trang nay tu la CA trinh doc lan trinh nghe — `ChapterPlayer` +
 * `MiniPlayer` + `ListenReporter` nam TREN dau, chiem het man hinh dau tien
 * truoc khi toi duoc chu. SAU: trai nghiem NGHE chuyen het sang `/listen/[id]`
 * (trang rieng, uu tien tap truoc/sau + chon tap + phu de dong bo); trang nay
 * chi con tieu de + mot lien ket "Nghe chương này" (khi co audio) + noi dung +
 * binh luan — dung nhu ten goi "trang doc".
 */

import Link from "next/link";
import { use, useCallback, useEffect } from "react";
import { api, type AudioTrack, type Chapter, type NovelBrief } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { ChapterComments } from "@/components/ChapterComments";
import { EmptyState, ErrorState, SkeletonList, formatNumber } from "@/components/ui";
import { IconBook, IconHeadphones } from "@/components/Icons";

export default function ChapterPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();

  // Backend tra kem `novel` trong chinh phan hoi cua chuong, nen khong con
  // phai goi them mot vong `/api/novels/{id}` chi de lay ten va anh bia.
  const fetchChapter = useCallback(() => api.getChapter(id), [id]);

  const { data, loading, error, missing, reload } = useAsyncData(fetchChapter);
  const chapter: Chapter | null = data?.chapter ?? null;
  const audio: AudioTrack | null = data?.audio ?? null;
  const novel: NovelBrief | null = data?.novel ?? null;

  /*
    Ghi con tro "Tiếp tục đọc" (Phần B, V4 visual completion) — MỘT LẦN khi mở
    trang, không phải mỗi lần cuộn. Chỉ khi đã đăng nhập: route yêu cầu token,
    và khách vãng lai không có "trang chủ của họ" để quay lại. Lỗi mạng ở đây
    KHÔNG được làm hỏng việc đọc — chỉ là tiện ích, không phải nội dung chính.
  */
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

  if (missing) {
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

  if (error || !chapter) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được chương."} onRetry={reload} />
      </div>
    );
  }

  const isOwner = profile?.user_id === chapter.owner_id;

  return (
    <div className="page">
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
        ) : isOwner ? (
          <Link className="btn btn-sm btn-ghost" href="/write">
            <span aria-hidden="true">🎙️</span> Tạo audio cho chương
          </Link>
        ) : null}
      </header>

      {/*
        Cot chu hep hon phan con lai cua trang. Mot dong dai ~68 ky tu la nguong
        mat con lan duoc tu cuoi dong nay sang dau dong sau ma khong lac; ca be
        rong 1180px thi doc mot chuong dai rat met.
      */}
      <section className="reader" aria-label="Nội dung chương">
        {chapter.content ? (
          <div className="prose">{chapter.content}</div>
        ) : (
          <p className="hint">Chương này chưa có nội dung.</p>
        )}
      </section>

      {/* Binh luan chuong — luon hien du co audio hay khong: day la binh
          luan ve NOI DUNG chuong, khong phai chi rieng ban audio. */}
      <div className="listen-col">
        <ChapterComments chapterId={chapter.chapter_id} />
      </div>

      {/*
        Loi ra o CUOI chuong. Nguoi vua doc xong dang o day, khong phai o dau
        trang — bat ho cuon nguoc len de tim duong sang chuong sau la mot viec
        thua.

        KHONG co nut "chuong truoc / chuong sau" o DAY: trang Nghe rieng
        (`/listen/[id]`) da co dieu do, dung `GET /api/novels/{id}` de lay ca
        danh sach chuong. Trang doc (trang nay) co ich hon khi chi dan thang
        ve trang truyen — nguoi con muon doc tiep se thay danh sach o do.
      */}
      {novel ? (
        <nav className="reader-foot" aria-label="Điều hướng chương">
          <Link className="btn" href={`/novels/${novel.novel_id}`}>
            <span aria-hidden="true">←</span> Danh sách chương
          </Link>
          <Link className="btn btn-ghost" href="/fanfic">
            Khám phá truyện khác
          </Link>
        </nav>
      ) : null}
    </div>
  );
}
