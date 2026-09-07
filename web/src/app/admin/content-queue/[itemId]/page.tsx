"use client";

/**
 * Chi tiet MOT muc trong hang doi san xuat noi dung.
 *
 * Cung ky luat voi trang danh sach: XEP viec, KHONG chay viec. Nut duy nhat
 * co tac dung ghi la "Xep lai", va no chi doi mot truong trang thai ve
 * `PENDING` — xem `server/content_queue_service.py::requeue_stage`.
 */

import Link from "next/link";
import { use, useCallback, useState } from "react";
import {
  adminApi,
  type ContentQueueRow,
  type ContentQueueStage,
  type ContentQueueStageState,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { DanhSachTrangThai, loiApi } from "@/components/AdminShell";

const STAGES: ReadonlyArray<{
  khoa: ContentQueueStage; nhan: string; moTa: string;
}> = [
  { khoa: "transcript", nhan: "Bóc lời",
    moTa: "Nhận dạng tiếng nói. Công đoạn đắt nhất — kết quả được lưu điểm dừng nên không bao giờ chạy lại." },
  { khoa: "translation", nhan: "Dịch",
    moTa: "Trung → Việt. Chỉ xong khi TOÀN BỘ đoạn đã dịch; thiếu một đoạn cũng tính là lỗi." },
  { khoa: "subtitle", nhan: "Phụ đề",
    moTa: "Dựng .srt, giữ nguyên mốc thời gian gốc." },
  { khoa: "dub", nhan: "Lồng tiếng",
    moTa: "Giọng Ngọc Huyền (Mới). Bỏ qua khi không yêu cầu." },
  { khoa: "draft", nhan: "Bản nháp",
    moTa: "Tạo bản nháp trên trang — không xuất bản." },
  { khoa: "render", nhan: "Kết xuất",
    moTa: "Ghép video. CHỈ chạy khi quyền cho phép phân phối lại media gốc." },
];

const NHAN_TT: Record<ContentQueueStageState, string> = {
  PENDING: "Chờ", RUNNING: "Đang chạy", DONE: "Xong",
  SKIPPED: "Bỏ qua có chủ đích", FAILED: "Lỗi",
};

const LOP_TT: Record<ContentQueueStageState, string> = {
  PENDING: "tt-cho", RUNNING: "tt-treo", DONE: "tt-duyet",
  SKIPPED: "tt-trong", FAILED: "tt-tuchoi",
};

function xepLaiDuoc(row: ContentQueueRow, stage: ContentQueueStage): boolean {
  if (row.ineligible) return false;
  if (stage === "render" && row.rights_mode !== "REHOST_ALLOWED") return false;
  const s = row.stages[stage];
  return s === "FAILED" || s === "RUNNING";
}

/** Vi sao mot cong doan KHONG xep lai duoc — noi thang, thay vi an nut di ma
    khong giai thich. */
function viSaoKhong(row: ContentQueueRow, stage: ContentQueueStage): string {
  if (row.ineligible) return "Mục đang bị hoãn vì nguồn không đủ điều kiện.";
  if (stage === "render" && row.rights_mode !== "REHOST_ALLOWED") {
    return `Quyền ${row.rights_mode} không cho phân phối lại media gốc.`;
  }
  const s = row.stages[stage];
  if (s === "DONE") return "Đã xong — xếp lại sẽ làm lại việc đã trả tiền rồi.";
  if (s === "SKIPPED") return "Đã bỏ qua có chủ đích.";
  if (s === "PENDING") return "Đang chờ tới lượt.";
  return "";
}

export default function TrangChiTietMuc(
  { params }: { params: Promise<{ itemId: string }> },
) {
  const { itemId } = use(params);
  const [dangXepLai, setDangXepLai] = useState("");
  const toast = useToast();

  const nap = useCallback(
    async () => (await adminApi.contentQueueItem(itemId)).item,
    [itemId],
  );
  const { data: row, loading, error, missing, reload } =
    useAsyncData<ContentQueueRow>(nap);

  const xepLai = useCallback(
    async (stage: ContentQueueStage) => {
      setDangXepLai(stage);
      try {
        await adminApi.contentQueueRequeue(itemId, stage);
        toast.ok("Đã xếp lại. Tiến trình xử lý sẽ nhặt nó ở lần quét kế tiếp.");
        reload();
      } catch (cause) {
        toast.error(loiApi(cause, "Không xếp lại được công đoạn này."));
      } finally {
        setDangXepLai("");
      }
    },
    [itemId, reload, toast],
  );

  if (missing) {
    return (
      <section className="stack">
        <p className="hint">Không tìm thấy mục này trong hàng đợi.</p>
        <p><Link href="/admin/content-queue">← Hàng đợi sản xuất</Link></p>
      </section>
    );
  }

  return (
    <section className="stack">
      <p className="hint">
        <Link href="/admin/content-queue">← Hàng đợi sản xuất</Link>
      </p>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!row}
                         onThuLai={reload}>
        {row ? (
          <div className="stack">
            <h2 className="section-title">{row.title || row.item_id}</h2>
            <p className="hint">
              {row.source_id} · {row.platform} · quyền {row.rights_mode}
            </p>

            {row.ineligible ? (
              <div className="admin-nhac">
                <div>
                  <strong>Mục này đang bị hoãn.</strong>
                  <div className="hint">
                    {row.last_error.replace(/^INELIGIBLE:\s*/, "")}
                  </div>
                  <div className="hint">
                    Siêu dữ liệu được giữ nguyên, không xoá gì. Mục sẽ quay lại
                    hàng đợi nếu ngưỡng thời lượng được nâng rồi chạy lại phép
                    đánh giá.
                  </div>
                </div>
              </div>
            ) : null}

            <div className="admin-bang-boc">
              <table className="admin-bang">
                <tbody>
                  <tr>
                    <th scope="row">Nguồn</th>
                    <td>
                      {row.source_url ? (
                        <a href={row.source_url} target="_blank" rel="noreferrer">
                          {row.source_url}
                        </a>
                      ) : "—"}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Điểm dừng bóc lời</th>
                    <td>
                      {row.has_transcript_checkpoint
                        ? "Đã có — chạy lại sẽ KHÔNG bóc lời lại"
                        : "Chưa có"}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Lỗi liên tiếp</th>
                    <td className="mono">{row.attempts}</td>
                  </tr>
                  <tr>
                    <th scope="row">Kết quả</th>
                    <td>
                      {row.novel_id ? (
                        <Link href={`/fanfic/${row.novel_id}`}>{row.novel_id}</Link>
                      ) : "chưa có bản nháp"}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Cập nhật</th>
                    <td className="hint mono">{row.updated_at}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="section-title">Các công đoạn</h3>
            <div className="admin-bang-boc">
              <table className="admin-bang">
                <thead>
                  <tr>
                    <th scope="col">Công đoạn</th>
                    <th scope="col">Trạng thái</th>
                    <th scope="col">Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {STAGES.map((s) => {
                    const tt = row.stages[s.khoa];
                    return (
                      <tr key={s.khoa}>
                        <td>
                          <strong>{s.nhan}</strong>
                          <div className="hint">{s.moTa}</div>
                        </td>
                        <td>
                          <span className={`tt ${LOP_TT[tt]}`}>{NHAN_TT[tt]}</span>
                        </td>
                        <td>
                          {xepLaiDuoc(row, s.khoa) ? (
                            <button type="button" className="btn btn-sm btn-ghost"
                                    disabled={dangXepLai === s.khoa}
                                    onClick={() => xepLai(s.khoa)}>
                              {dangXepLai === s.khoa ? "Đang xếp…" : "Xếp lại"}
                            </button>
                          ) : (
                            <span className="hint">{viSaoKhong(row, s.khoa)}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {row.last_error && !row.ineligible ? (
              <>
                <h3 className="section-title">
                  {row.waiting ? "Đang chờ" : "Lỗi gần nhất"}
                </h3>
                <pre className="mono">{row.last_error}</pre>
              </>
            ) : null}
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
