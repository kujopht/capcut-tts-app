"use client";

/** Doc chuong: trinh phat audio o tren, noi dung o duoi. */

import Link from "next/link";
import { use, useCallback } from "react";
import { api, type AudioTrack, type Chapter, type NovelBrief } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { AudioPlayer } from "@/components/AudioPlayer";
import { EmptyState, ErrorState, SkeletonList, formatNumber } from "@/components/ui";
import { NovelCover } from "@/components/NovelCover";

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
  const audioOutdated = Boolean(data?.audio_outdated);

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
      <nav aria-label="Đường dẫn">
        <Link href={`/novels/${chapter.novel_id}`} className="hint crumb">
          ← {novel?.title ?? "Về truyện"}
        </Link>
      </nav>

      <header className="stack-2 reader-head">
        <h1 className="page-title">{chapter.title}</h1>
        <span className="hint">
          {formatNumber(chapter.char_count)} ký tự
          {novel ? ` · ${novel.title}` : ""}
        </span>
      </header>

      {/*
        Khu nghe di theo CUNG cot voi chu. Truoc day no rong het trang trong
        khi chu chi rong 68 ky tu, va o trang chua co audio thi mot hop rong
        1130px cho mot cau ngan chiem het man hinh dau tien — nguoi doc phai
        cuon qua no moi toi duoc chuong.
      */}
      {audio ? (
        <div className="stack reader-col">
          {/* M4: audio van phat duoc va van tai duoc — chi canh bao rang no
              duoc tao truoc lan sua noi dung gan nhat. Chu so huu duoc chi
              duong tao lai; nguoi doc chi can biet de khong ngo ngang. */}
          {audioOutdated ? (
            <div className="alert alert-warn" role="status">
              <span aria-hidden="true">⚠</span>
              <span className="stack-2">
                <span>
                  Chương này đã được sửa sau khi tạo audio, nên{" "}
                  <strong>audio có thể không còn khớp</strong> với nội dung bên
                  dưới. Bản audio hiện tại vẫn nghe và tải được.
                </span>
                {/* Nut that, khong phai lien ket trong cau: vung bam du to o
                    mobile, va M4 yeu cau duong dan RO RANG sang cho tao lai. */}
                {isOwner ? (
                  <Link className="btn btn-sm" href="/write">
                    Tạo lại audio trong khu vực tác giả
                  </Link>
                ) : null}
              </span>
            </div>
          ) : null}
          <div className="listen">
            <NovelCover
              novelId={chapter.novel_id}
              title={novel?.title ?? chapter.title}
              coverUrl={novel?.cover_url}
              size="thumb"
            />
            <div className="listen-player">
              <AudioPlayer chapterId={chapter.chapter_id} title={chapter.title} />
            </div>
          </div>
        </div>
      ) : (
        <div className="reader-col">
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
              ) : undefined
            }
          />
        </div>
      )}

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

      {/*
        Loi ra o CUOI chuong. Nguoi vua doc xong dang o day, khong phai o dau
        trang — bat ho cuon nguoc len de tim duong sang chuong sau la mot viec
        thua.

        KHONG co nut "chuong truoc / chuong sau": `GET /api/chapters/{id}` tra
        ve `NovelBrief`, tuc la KHONG mang danh sach chuong anh em. Bia hai nut
        do se phai goi them mot vong `/api/novels/{id}` moi lan mo chuong. Ghi
        lai trong bao cao thay vi tu them.
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
