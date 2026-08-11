"use client";

/**
 * Bảng tin cộng đồng.
 *
 * KHÔNG đòi đăng nhập. Khách vãng lai thấy bảng tin khám phá; người đã theo dõi
 * ai đó thấy bài của những người đó lên trước. Một trang cộng đồng trả 401 cho
 * khách là một cánh cửa đóng, và nội dung ở đây vốn là công khai.
 *
 * Người CHƯA theo dõi ai KHÔNG thấy trang trống — họ thấy bài mới nhất của cả hệ
 * thống, kèm một dòng nói rõ. Một bảng tin rỗng ở lần đầu vào là một lý do để
 * không quay lại.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  social,
  type FeedPage,
  type Novel,
  type Post,
  type ServerLimits,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { PageHeader, SkeletonList, ErrorState, EmptyState } from "@/components/ui";
import { PostCard } from "@/components/PostCard";
import { PostComposer } from "@/components/PostComposer";

export default function CommunityPage() {
  const { profile, loading: dangTaiPhien } = useSession();
  const [trang, setTrang] = useState<FeedPage | null>(null);
  const [limits, setLimits] = useState<ServerLimits | null>(null);
  const [truyenCuaToi, setTruyenCuaToi] = useState<Novel[]>([]);
  const [loi, setLoi] = useState("");
  const [dangThem, setDangThem] = useState(false);

  const tai = useCallback(() => {
    setLoi("");
    social
      .feed()
      .then(setTrang)
      .catch((e) =>
        setLoi(e instanceof ApiError ? e.message : "Không tải được bảng tin."),
      );
  }, []);

  /*
    `queueMicrotask` chu khong goi thang `tai()`.

    `tai()` mo dau bang `setLoi("")` — mot `setState` DONG BO trong than effect,
    va quy tac `react-hooks/set-state-in-effect` cam dieu do. Mot vi tac vu chay
    sau khi cay da commit va TRUOC khi trinh duyet ve, nen nguoi dung khong thay
    khac biet nao. Cung ky thuat da dung o `NavIndicator`.
  */
  useEffect(() => {
    queueMicrotask(tai);
  }, [tai, profile]);

  /* Giới hạn của máy chủ. Lỗi ở đây KHÔNG hiện ra: hộp soạn bài vẫn dùng được
     với con số dự phòng, và máy chủ vẫn là nơi cưỡng chế. */
  useEffect(() => {
    social.limits().then(setLimits).catch(() => {});
  }, []);

  /* Truyện đã xuất bản của chính mình — để đăng "cập nhật truyện". Chỉ hỏi khi
     người dùng LÀ tác giả đã duyệt: với mọi người khác đây là một truy vấn chắc
     chắn trả về rỗng. */
  const laTacGia = profile?.author_status === "approved";
  useEffect(() => {
    if (!laTacGia) return;
    api
      .listNovels(true)
      .then((r) =>
        setTruyenCuaToi(r.novels.filter((n) => n.state === "published")),
      )
      .catch(() => {});
  }, [laTacGia]);

  const themVaoDau = useCallback((bai: Post) => {
    setTrang((truoc) =>
      truoc
        ? { ...truoc, items: [bai, ...truoc.items], total: truoc.total + 1 }
        : truoc,
    );
  }, []);

  const themTrang = useCallback(async () => {
    if (!trang) return;
    setDangThem(true);
    try {
      const ra = await social.feed(trang.limit, trang.items.length);
      setTrang({ ...ra, items: [...trang.items, ...ra.items] });
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không tải thêm được.");
    } finally {
      setDangThem(false);
    }
  }, [trang]);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Quảng trường"
        title="Cộng đồng"
        lead={
          trang?.personalized
            ? "Bài mới từ những người bạn theo dõi."
            : "Bài mới nhất từ khắp Fanfic World."
        }
      />

      {profile ? (
        <PostComposer
          limits={limits}
          /* Loc o day chu khong dat lai trang thai khi `author_status` doi:
             mot danh sach da tai ve roi van dung, va mot nguoi vua bi treo thi
             chi don gian la khong con lua chon nao. */
          storyOptions={
            laTacGia
              ? truyenCuaToi.map((n) => ({
                  novel_id: n.novel_id,
                  title: n.title,
                }))
              : []
          }
          onPosted={themVaoDau}
        />
      ) : dangTaiPhien ? null : (
        <p className="hint">
          <Link href="/login?next=%2Fcommunity">Đăng nhập</Link> để đăng bài,
          thích và bình luận.
        </p>
      )}

      {/* Nói rõ khi danh sách theo dõi bị cắt, thay vì im lặng bỏ bớt. */}
      {trang?.following_truncated ? (
        <p className="hint">
          Bạn theo dõi rất nhiều người — bảng tin đang hiện bài của những người
          bạn theo dõi gần nhất.
        </p>
      ) : null}

      {loi ? <ErrorState message={loi} onRetry={tai} /> : null}

      {trang === null && !loi ? (
        <SkeletonList count={3} />
      ) : trang && trang.items.length === 0 ? (
        <EmptyState
          title="Chưa có bài nào"
          hint={
            profile
              ? "Hãy là người đầu tiên chia sẻ điều gì đó."
              : "Đăng nhập để bắt đầu."
          }
        />
      ) : (
        <div className="stack">
          {(trang?.items ?? []).map((bai) => (
            <PostCard
              key={bai.post_id}
              post={bai}
              limits={limits}
              onChange={(moi) =>
                setTrang((truoc) =>
                  truoc
                    ? {
                        ...truoc,
                        items: truoc.items.map((x) =>
                          x.post_id === moi.post_id ? moi : x,
                        ),
                      }
                    : truoc,
                )
              }
              onDeleted={(id) =>
                setTrang((truoc) =>
                  truoc
                    ? {
                        ...truoc,
                        items: truoc.items.filter((x) => x.post_id !== id),
                        total: Math.max(0, truoc.total - 1),
                      }
                    : truoc,
                )
              }
            />
          ))}
        </div>
      )}

      {trang && trang.items.length < trang.total ? (
        <button
          type="button"
          className="btn btn-ghost"
          disabled={dangThem}
          onClick={themTrang}
        >
          {dangThem ? "Đang tải…" : "Xem thêm"}
        </button>
      ) : null}
    </div>
  );
}
