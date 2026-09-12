"use client";

/**
 * Kiểm duyệt MỘT tác phẩm — đọc rồi mới quyết định.
 *
 * VÌ SAO TRANG NÀY TỒN TẠI. Trước bản này, danh sách quản trị liên kết tới
 * `/novels/{id}`, mà đường công khai trả **404 cho mọi bản nháp** — tức là
 * cho đúng những dòng người quản trị cần mở nhất. Nên thao tác "xem trước rồi
 * duyệt" không thực hiện được, và luồng
 * SCRAPED → DRAFT → NGƯỜI XEM → XUẤT BẢN đứt ngay ở giữa.
 *
 * Trang này đọc qua `/api/admin/novels/{id}` — một bề mặt RIÊNG, đã khoá bằng
 * `Depends`. Đường công khai không hề đổi, và điều đó là có chủ đích: thêm một
 * nhánh "nếu là admin" vào `_may_read` sẽ làm MỌI route đọc công khai thừa kế
 * nó cùng lúc.
 *
 * NGƯỜI VẪN LÀ NGƯỜI QUYẾT ĐỊNH. Không có nút "duyệt tất cả", không tự động
 * xuất bản. Toàn văn hiện ngay trên trang vì một quyết định xuất bản mà chưa
 * đọc nội dung thì không phải là kiểm duyệt.
 */

import Link from "next/link";
import { useCallback, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { adminApi } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { errorMessage } from "@/lib/session";
import { DanhSachTrangThai } from "@/components/AdminShell";
import { ConfirmDialog, formatNumber } from "@/components/ui";
import { IconBook } from "@/components/Icons";

/** Bao nhiêu ký tự của mỗi chương hiện ngay; phần còn lại bấm để mở. */
const XEM_TRUOC = 1200;

export default function AdminStoryReview() {
  const params = useParams<{ id: string }>();
  const novelId = String(params?.id ?? "");
  const router = useRouter();
  const toast = useToast();

  const nap = useCallback(() => adminApi.novel(novelId), [novelId]);
  const { data, loading, error, reload } = useAsyncData(nap);

  const [dangChay, setDangChay] = useState(false);
  const [hoiXuatBan, setHoiXuatBan] = useState(false);
  const [hoiGoXuong, setHoiGoXuong] = useState(false);
  const [moRong, setMoRong] = useState<Record<string, boolean>>({});

  const n = data?.novel;
  const chuong = data?.chapters ?? [];
  const daXuatBan = n?.state === "published";
  // `chapters.length` chưa đủ: 13 truyện đang sống trên trang đều có đúng một
  // chương VÀ `char_count === 0` (nhập từ audio dài tập).
  const soChuongCoChu = chuong.filter((c) => c.content.trim().length > 0).length;

  async function chay(viec: () => Promise<unknown>, xong: string) {
    setDangChay(true);
    try {
      await viec();
      toast.ok(xong);
      reload();
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangChay(false);
      setHoiXuatBan(false);
      setHoiGoXuong(false);
    }
  }

  return (
    <section className="stack">
      <div className="row row-spread">
        <h2 className="section-title section-title-icon">
          <IconBook size={19} /> Duyệt tác phẩm
        </h2>
        <Link className="btn btn-sm" href="/admin/stories">
          ← Về danh sách
        </Link>
      </div>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={!data}
        onThuLai={reload}
      >
        {n ? (
          <div className="stack-3">
            {/* ------------------------------------------- siêu dữ liệu */}
            <div className="card stack-2">
              <div className="row row-spread">
                <h3 className="section-title-sm">{n.title}</h3>
                <span
                  className={`tt ${daXuatBan ? "tt-duyet" : "tt-trong"}`}
                >
                  {daXuatBan ? "Đã xuất bản" : "Bản nháp"}
                </span>
              </div>

              <dl className="admin-ho-so">
                <Muc nhan="Tác giả nguồn" gia_tri={n.external_author_name} />
                <Muc
                  nhan="Chủ sở hữu"
                  gia_tri={n.owner ? `@${n.owner.username}` : n.owner_id}
                />
                <Muc nhan="Ngôn ngữ" gia_tri={n.language} />
                <Muc nhan="Thẻ" gia_tri={(n.tags ?? []).join(", ")} />
                <Muc nhan="Chương" gia_tri={String(chuong.length)} />
                <Muc
                  nhan="Tổng độ dài"
                  gia_tri={`${formatNumber(data.total_chars)} ký tự`}
                />
                <Muc
                  nhan="Ảnh bìa"
                  gia_tri={n.cover_url ? "có" : "chưa có"}
                />
                <Muc
                  nhan="Cập nhật"
                  gia_tri={new Date(n.updated_at).toLocaleString("vi-VN")}
                />
              </dl>

              {n.description ? <p className="hint">{n.description}</p> : null}

              {n.external_source_url ? (
                <p className="hint">
                  Nguồn:{" "}
                  <a
                    href={n.external_source_url}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                  >
                    {n.external_source_url} ↗
                  </a>
                </p>
              ) : null}
            </div>

            {/* ------------------------------------------------ cảnh báo */}
            {soChuongCoChu === 0 ? (
              <p className="card admin-nhac">
                Không chương nào có văn bản đọc được. Xuất bản sẽ bị từ chối —
                một trang trống không phải một tác phẩm.
              </p>
            ) : null}

            {/* ------------------------------------------------ thao tác */}
            <div className="row">
              {daXuatBan ? (
                <button
                  type="button"
                  className="btn"
                  disabled={dangChay}
                  onClick={() => setHoiGoXuong(true)}
                >
                  Gỡ xuống
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={dangChay || soChuongCoChu === 0}
                  onClick={() => setHoiXuatBan(true)}
                >
                  Xuất bản
                </button>
              )}
              {daXuatBan ? (
                <Link className="btn btn-ghost" href={`/novels/${n.novel_id}`}>
                  Xem trang công khai ↗
                </Link>
              ) : null}
            </div>

            {/* ------------------------------------------- nội dung thật */}
            <h3 className="section-title-sm">Nội dung</h3>
            {chuong.length === 0 ? (
              <p className="hint">Chưa có chương nào.</p>
            ) : (
              <div className="stack-2">
                {chuong.map((c) => {
                  const dai = c.content.length > XEM_TRUOC;
                  const mo = moRong[c.chapter_id];
                  return (
                    <div key={c.chapter_id} className="card stack-2">
                      <div className="row row-spread">
                        <strong>
                          {c.order_index}. {c.title}
                        </strong>
                        <span className="hint mono">
                          {formatNumber(c.char_count)} ký tự
                        </span>
                      </div>
                      {c.content.trim() ? (
                        <>
                          <p className="prose admin-xem-truoc">
                            {dai && !mo
                              ? `${c.content.slice(0, XEM_TRUOC)}…`
                              : c.content}
                          </p>
                          {dai ? (
                            <button
                              type="button"
                              className="btn btn-sm btn-ghost"
                              onClick={() =>
                                setMoRong((v) => ({
                                  ...v,
                                  [c.chapter_id]: !mo,
                                }))
                              }
                            >
                              {mo ? "Thu gọn" : "Đọc toàn văn"}
                            </button>
                          ) : null}
                        </>
                      ) : (
                        <p className="hint">
                          Chương này không có văn bản (bản nhập từ audio).
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}
      </DanhSachTrangThai>

      <ConfirmDialog
        open={hoiXuatBan}
        title="Xuất bản tác phẩm này?"
        body="Sau khi xuất bản, bất kỳ ai cũng đọc được. Gỡ xuống lại được."
        confirmLabel="Xuất bản"
        busy={dangChay}
        onCancel={() => setHoiXuatBan(false)}
        onConfirm={() =>
          chay(() => adminApi.publishNovel(novelId), "Đã xuất bản.")
        }
      />
      <ConfirmDialog
        open={hoiGoXuong}
        title="Gỡ tác phẩm này xuống?"
        body="Tác phẩm trở lại bản nháp và biến mất khỏi trang công khai."
        confirmLabel="Gỡ xuống"
        danger
        busy={dangChay}
        onCancel={() => setHoiGoXuong(false)}
        onConfirm={() =>
          chay(() => adminApi.unpublishNovel(novelId), "Đã gỡ xuống.")
        }
      />
    </section>
  );
}

function Muc({ nhan, gia_tri }: { nhan: string; gia_tri?: string }) {
  return (
    <>
      <dt className="hint">{nhan}</dt>
      <dd>{gia_tri && gia_tri.trim() ? gia_tri : <span className="hint">—</span>}</dd>
    </>
  );
}
