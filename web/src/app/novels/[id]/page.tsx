"use client";

/** Chi tiet truyen: thong tin, danh sach chuong kem trang thai audio. */

import Link from "next/link";
import { use, useCallback } from "react";
import { api, type Chapter, type Novel } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  EmptyState,
  ErrorState,
  SkeletonList,
  formatDate,
  formatNumber,
} from "@/components/ui";
import { NovelCover } from "@/components/NovelCover";
import { FollowButton } from "@/components/FollowButton";

/**
 * Tien do tac pham -> nhan tieng Viet.
 *
 * Gia tri khong nam trong bang thi TRA VE NGUYEN VAN, khong doi thanh "Khac"
 * hay chuoi rong: backend co the them trang thai moi truoc frontend, va luc do
 * hien dung chu cua backend van dung hon la giau no di.
 */
const NHAN_TIEN_DO: Record<string, string> = {
  ongoing: "Đang ra",
  completed: "Hoàn thành",
  hiatus: "Tạm ngưng",
  abandoned: "Đã bỏ",
};

function nhanTienDo(status: string): string {
  return NHAN_TIEN_DO[status] ?? status;
}

export default function NovelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();

  // MOT request duy nhat, du truyen co bao nhieu chuong: `has_audio` da nam
  // san trong danh sach chuong. Truoc day cho nay goi them `/api/chapters/{id}`
  // cho tung chuong chi de doc mot gia tri boolean.
  const fetchNovel = useCallback(() => api.getNovel(id), [id]);

  const { data, loading, error, missing, reload } = useAsyncData(fetchNovel);
  const novel: Novel | null = data?.novel ?? null;
  const chapters: Chapter[] = data?.chapters ?? [];

  if (loading) {
    return (
      <div className="page">
        <div className="sk sk-title" style={{ height: 32, width: "40%" }} />
        <SkeletonList count={5} />
      </div>
    );
  }

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy truyện này"
          hint="Truyện có thể đã bị xoá hoặc chưa được xuất bản."
          action={
            <Link className="btn btn-primary" href="/fanfic" prefetch={false}>
              Về trang khám phá
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !novel) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được truyện."} onRetry={reload} />
      </div>
    );
  }

  const isOwner = profile?.user_id === novel.owner_id;
  // `has_audio` da co san trong danh sach chuong (xem ghi chu o `fetchNovel`),
  // nen tong hop nay khong ton them request nao.
  const soChuongCoAudio = chapters.filter((c) => c.has_audio).length;

  return (
    <div className="page">
      <nav aria-label="Đường dẫn">
        <Link href="/fanfic" className="hint crumb" prefetch={false}>
          ← Khám phá Fanfic
        </Link>
      </nav>

      {/*
        Bia va chu nam CANH nhau tren man hinh rong, chong len nhau o mobile
        (xem `.novel-head`). Ban cu xep bia 16:6 nam tren roi chu ben duoi: o
        desktop, bia rong 1180px chiem gan het man hinh dau tien va day ten
        truyen xuong duoi nep gap.
      */}
      <header className="novel-head">
        <div className="novel-head-cover">
          <NovelCover
            novelId={novel.novel_id}
            title={novel.title}
            coverUrl={novel.cover_url}
            size="card"
          />
        </div>

        <div className="stack-2 novel-head-body">
          <div className="row novel-head-tags">
            <span className={`badge ${novel.state === "published" ? "badge-ok" : ""}`}>
              {novel.state === "published" ? "Đã xuất bản" : "Bản nháp"}
            </span>
            {/*
              Tien do TAC PHAM (`status`), khac han trang thai XUAT BAN
              (`state`) o badge ben canh: mot truyen da hoan thanh van co the
              dang la ban nhap. Hai khai niem nay tu truoc van bi bo mat mot
              nua o day, du backend luon tra ve ca hai.
            */}
            {novel.status ? (
              <span className="badge">{nhanTienDo(novel.status)}</span>
            ) : null}
            {novel.tags.map((tag) => (
              <span key={tag} className="badge">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="page-title">{novel.title}</h1>
          <p className="lead lead-narrow">
            {novel.description || "Chưa có mô tả."}
          </p>
          <span className="hint">
            {chapters.length} chương
            {soChuongCoAudio > 0 ? ` · ${soChuongCoAudio} chương có audio` : ""}
            {" · cập nhật "}
            {formatDate(novel.updated_at)}
          </span>

          {/*
            GHI CONG NGUON. Kho nay chua fanfic NHAP tu noi khac, nen ten tac
            gia goc va duong ve nguon khong phai "metadata cho dep" — do la dieu
            toi thieu phai hien. Backend luon tra ve ba truong nay; trang nay
            truoc day khong ve mot cai nao.

            `nofollow` tren lien ket ngoai: day la link do nguoi nhap dat, khong
            phai mot su gioi thieu cua Fanfic World.
          */}
          {novel.external_author_name || novel.external_source_url || novel.language ? (
            <span className="hint novel-head-source">
              {novel.external_author_name ? (
                <span>Tác giả gốc: {novel.external_author_name}</span>
              ) : null}
              {novel.language ? <span>Ngôn ngữ gốc: {novel.language}</span> : null}
              {novel.external_source_url ? (
                <a
                  href={novel.external_source_url}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                >
                  Nguồn gốc ↗
                </a>
              ) : null}
            </span>
          ) : null}

          {/*
            Nguon cong bo NHIEU chuong hon so dang co o day. KHONG che con so
            nay va cung khong "hoa giai" hai con so: mot ban nhap moi nhap duoc
            15/60 chuong la su that ma nguoi doc can biet truoc khi bat dau.
          */}
          {novel.external_chapter_count > 0 &&
          novel.external_chapter_count !== chapters.length ? (
            <span className="hint">
              Nguồn công bố {formatNumber(novel.external_chapter_count)} chương
            </span>
          ) : null}

          <div className="row novel-head-actions">
            {chapters.length > 0 ? (
              <Link
                className="btn btn-primary"
                href={`/chapters/${chapters[0].chapter_id}`}
              >
                Đọc từ đầu
              </Link>
            ) : null}
            {isOwner ? (
              <Link className="btn" href="/write" prefetch={false}>
                Quản lý truyện
              </Link>
            ) : null}
            {/*
              Theo dõi truyện — để được thông báo khi có chương mới.

              KHÔNG hiện với chủ sở hữu: một tác giả tự theo dõi truyện của mình
              thì backend cũng không gửi thông báo (xem `notify_new_chapter`),
              nên cái nút đó là một lời hứa suông.

              Cũng không hiện với bản nháp: `data.follow` chỉ có mặt với truyện
              đã xuất bản, nên phép kiểm này đi theo đúng sự thật của backend
              thay vì đoán lại nó ở đây.
            */}
            {!isOwner && data?.follow ? (
              <FollowButton
                kind="story"
                targetId={novel.novel_id}
                initialFollowing={data.follow.following}
                initialCount={data.follow.follower_count}
                label="Theo dõi truyện"
              />
            ) : null}
          </div>
        </div>
      </header>

      <section className="stack" aria-label="Danh sách chương">
        <h2 className="section-title">Danh sách chương</h2>
        {chapters.length === 0 ? (
          <EmptyState
            icon="📄"
            title="Truyện chưa có chương nào"
            action={
              isOwner ? (
                <Link className="btn btn-primary" href="/write" prefetch={false}>
                  Thêm chương đầu tiên
                </Link>
              ) : undefined
            }
          />
        ) : (
          <div className="list">
            {chapters.map((chapter, index) => (
              // KHONG con boc ca hang trong <Link>: the <a> khong duoc chua
              // <button>/<a> khac, va nut Doc/Nghe phai nam ngay trong hang.
              // Tieu de moi la lien ket (toi trang Doc), cac nut la anh em.
              <div key={chapter.chapter_id} className="list-item">
                <span className="list-index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="stack-2 list-main">
                  <Link
                    href={`/chapters/${chapter.chapter_id}`}
                    className="truncate list-title"
                  >
                    {chapter.title}
                  </Link>
                  <span className="hint">
                    {formatNumber(chapter.char_count)} ký tự
                  </span>
                </span>

                <span className="list-actions">
                  {/* Doc va Nghe la HAI trai nghiem rieng (Phan 2A) — Doc
                      luon di duoc (chua co audio van doc duoc chu), Nghe chi
                      hien khi da co audio va dan sang trang Nghe rieng,
                      KHONG con mo mot trinh phat ngay trong hang nay nua. */}
                  <Link className="btn btn-sm" href={`/chapters/${chapter.chapter_id}`}>
                    <span aria-hidden="true">📖</span> Đọc
                  </Link>
                  {chapter.has_audio ? (
                    <>
                      {/* M4: audio con nghe duoc, chi la co the khong khop
                          noi dung moi nhat. Noi ro thay vi im lang. */}
                      {chapter.audio_outdated ? (
                        <span
                          className="badge badge-warn"
                          title="Chương đã sửa sau khi tạo audio — audio có thể không còn khớp"
                        >
                          <span aria-hidden="true">⚠</span> Audio cũ
                        </span>
                      ) : null}
                      <Link
                        className="btn btn-sm btn-primary"
                        href={`/listen/${chapter.chapter_id}`}
                      >
                        <span aria-hidden="true">▶</span> Nghe
                      </Link>
                    </>
                  ) : (
                    <span className="badge">Chưa có audio</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
