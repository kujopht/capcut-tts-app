"use client";

/**
 * Cộng đồng — trang TỔNG HỢP, không thay thế /admin/posts, /admin/reports,
 * /admin/comments. Ba trang đó đã có đủ logic kiểm duyệt (gỡ/phục hồi, đóng
 * báo cáo) và đây KHÔNG lặp lại logic đó — trang này chỉ GHÉP số liệu đọc
 * được (`adminSocial.overview`) và một lát cắt xem trước (5 dòng mới nhất
 * của mỗi loại, cùng API mà trang đích dùng) kèm liên kết sang đúng hàng đợi
 * và tới bài/hồ sơ công khai.
 *
 * KHÔNG có nút gỡ/phục hồi ở đây — mọi thao tác kiểm duyệt thật vẫn chỉ nằm
 * ở ba trang gốc, để không có hai nơi cùng gọi cùng một API ghi.
 */

import Link from "next/link";
import { useCallback } from "react";
import {
  adminSocial,
  type AdminPost,
  type ContentReport,
  type SocialOverview,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai, OSo } from "@/components/AdminShell";
import { formatDate } from "@/components/ui";
import { IconFeather, IconMegaphone, IconShield } from "@/components/Icons";

const TEN_LY_DO: Record<string, string> = {
  spam: "Spam / quảng cáo",
  harassment: "Quấy rối",
  inappropriate: "Không phù hợp",
  copyright: "Bản quyền",
  other: "Khác",
};

function BaoCaoGanDay({ items }: { items: ContentReport[] }) {
  if (items.length === 0) {
    return <p className="hint admin-khong-viec">Không có báo cáo nào đang mở.</p>;
  }
  return (
    <ul className="stack-2">
      {items.map((bc) => (
        <li key={bc.report_id} className="card admin-nhac" style={{ alignItems: "flex-start" }}>
          <IconShield size={17} />
          <span className="stack-2" style={{ flex: 1 }}>
            <span>
              <strong>{TEN_LY_DO[bc.reason] ?? bc.reason}</strong>{" "}
              — {bc.target_kind === "post" ? "bài đăng" : "bình luận"} của{" "}
              {bc.target_owner?.username ? (
                <Link href={`/u/${bc.target_owner.username}`}>
                  {bc.target_owner.display_name || bc.target_owner.username}
                </Link>
              ) : (
                bc.target_owner?.display_name || "người dùng"
              )}
            </span>
            <span className="hint">{formatDate(bc.created_at)}</span>
          </span>
          {bc.context_url ? (
            <Link className="btn btn-ghost btn-sm" href={bc.context_url}>
              Xem nguồn
            </Link>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function BaiDangGanDay({ items }: { items: AdminPost[] }) {
  if (items.length === 0) {
    return <p className="hint admin-khong-viec">Chưa có bài đăng nào.</p>;
  }
  return (
    <ul className="stack-2">
      {items.map((b) => (
        <li key={b.post_id} className="card admin-nhac" style={{ alignItems: "flex-start" }}>
          <IconMegaphone size={17} />
          <span className="stack-2" style={{ flex: 1 }}>
            <Link href={`/posts/${b.post_id}`} className="admin-bai-chu">
              {b.text
                ? b.text.slice(0, 80) + (b.text.length > 80 ? "…" : "")
                : "(chỉ có ảnh)"}
            </Link>
            <span className="hint">
              {b.author?.username ? (
                <Link href={`/u/${b.author.username}`}>
                  {b.author.display_name || b.author.username}
                </Link>
              ) : (
                b.author?.display_name || "—"
              )}{" "}
              · {formatDate(b.created_at)}
              {b.open_reports > 0 ? (
                <> · <span className="badge badge-warn">{b.open_reports} báo cáo</span></>
              ) : null}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function AdminCommunityPage() {
  const napTongQuan = useCallback(() => adminSocial.overview(), []);
  const { data: tongQuan, loading: taiTongQuan, error: loiTongQuan, reload: taiLaiTongQuan } =
    useAsyncData<SocialOverview>(napTongQuan);

  const napBaoCao = useCallback(() => adminSocial.reports("open", "", 5, 0), []);
  const { data: dsBaoCao, loading: taiBaoCao, error: loiBaoCao, reload: taiLaiBaoCao } =
    useAsyncData(napBaoCao);

  const napBaiDang = useCallback(() => adminSocial.posts("", 5, 0), []);
  const { data: dsBaiDang, loading: taiBaiDang, error: loiBaiDang, reload: taiLaiBaiDang } =
    useAsyncData(napBaiDang);

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconMegaphone size={19} /> Cộng đồng
      </h2>
      <p className="hint">
        Tổng hợp bài đăng, báo cáo và bình luận — thao tác gỡ/phục hồi/đóng báo
        cáo vẫn thực hiện ở từng trang đích, không lặp lại ở đây.
      </p>

      <DanhSachTrangThai
        dangTai={taiTongQuan}
        loi={loiTongQuan}
        rong={!tongQuan}
        onThuLai={taiLaiTongQuan}
      >
        {tongQuan ? (
          <div className="stat-grid admin-luoi">
            <OSo nhan="Báo cáo đang mở" so={tongQuan.open_reports} />
            <OSo nhan="Tổng số báo cáo" so={tongQuan.total_reports} />
            <OSo nhan="Tổng số bài đăng" so={tongQuan.total_posts} />
            <OSo nhan="Bài đăng đã gỡ" so={tongQuan.removed_posts} />
          </div>
        ) : null}
      </DanhSachTrangThai>

      <div className="bento-grid">
        <Link href="/admin/reports" className="card stack-2">
          <h3 className="section-title section-title-icon">
            <IconShield size={17} /> Báo cáo
          </h3>
          <p className="hint">
            Hàng đợi báo cáo nội dung — lọc theo Đang mở/Đã xử lý/Đã bỏ qua/Tất
            cả, gỡ hoặc đóng báo cáo.
          </p>
        </Link>
        <Link href="/admin/posts" className="card stack-2">
          <h3 className="section-title section-title-icon">
            <IconMegaphone size={17} /> Bài đăng
          </h3>
          <p className="hint">Tìm theo nội dung, gỡ/phục hồi từng bài.</p>
        </Link>
        <Link href="/admin/comments" className="card stack-2">
          <h3 className="section-title section-title-icon">
            <IconFeather size={17} /> Bình luận
          </h3>
          <p className="hint">
            Duyệt bình luận bài đăng/chương/tập Animation, gỡ/phục hồi.
          </p>
        </Link>
      </div>

      <div>
        <h3 className="section-title-sm">Báo cáo mới nhất đang mở</h3>
        <DanhSachTrangThai
          dangTai={taiBaoCao}
          loi={loiBaoCao}
          rong={!!dsBaoCao && dsBaoCao.items.length === 0}
          onThuLai={taiLaiBaoCao}
        >
          {dsBaoCao ? <BaoCaoGanDay items={dsBaoCao.items} /> : null}
        </DanhSachTrangThai>
      </div>

      <div>
        <h3 className="section-title-sm">Bài đăng mới nhất</h3>
        <DanhSachTrangThai
          dangTai={taiBaiDang}
          loi={loiBaiDang}
          rong={!!dsBaiDang && dsBaiDang.items.length === 0}
          onThuLai={taiLaiBaiDang}
        >
          {dsBaiDang ? <BaiDangGanDay items={dsBaiDang.items} /> : null}
        </DanhSachTrangThai>
      </div>
    </section>
  );
}
