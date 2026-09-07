"use client";

/**
 * Hang doi san xuat noi dung (`content_queue`).
 *
 * TRANG NAY XEP VIEC VA QUAN LY VIEC. NO KHONG CHAY VIEC.
 *
 * Nut "Xep lai" chi doi MOT truong trang thai ve `PENDING` qua
 * `POST /api/admin/content-queue/{id}/requeue`; tien trinh orchestrator DUY
 * NHAT (`scripts/chinese_media_orchestrator.py`) nhat no o lan quet ke tiep.
 * Khong co duong nao tu day khoi chay mot tien trinh — va do khong phai so
 * thich kien truc: Appwrite khong co cap nhat co dieu kien va `content_queue`
 * chua co truong lease, nen neu moi cu bam nut sinh mot ban tieu thu thi
 * chung se gianh cung mot muc va ghi de ket qua cua nhau.
 *
 * Dung lai DUNG bon route backend da co. Khong route moi.
 */

import Link from "next/link";
import { useCallback, useState } from "react";
import {
  adminApi,
  type ContentQueueList,
  type ContentQueueOverall,
  type ContentQueueRow,
  type ContentQueueStage,
  type ContentQueueStageState,
  type ContentQueueSummary,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { DanhSachTrangThai, loiApi } from "@/components/AdminShell";
import { IconInbox } from "@/components/Icons";

const STAGES: ReadonlyArray<{ khoa: ContentQueueStage; nhan: string }> = [
  { khoa: "transcript", nhan: "Bóc lời" },
  { khoa: "translation", nhan: "Dịch" },
  { khoa: "subtitle", nhan: "Phụ đề" },
  { khoa: "dub", nhan: "Lồng tiếng" },
  { khoa: "draft", nhan: "Bản nháp" },
  { khoa: "render", nhan: "Kết xuất" },
];

const BO_LOC: ReadonlyArray<{ khoa: "" | ContentQueueOverall; nhan: string }> = [
  { khoa: "", nhan: "Tất cả" },
  { khoa: "PENDING", nhan: "Chờ chạy" },
  { khoa: "RUNNING", nhan: "Đang chạy" },
  { khoa: "FAILED", nhan: "Lỗi" },
  { khoa: "COMPLETE", nhan: "Hoàn tất" },
  { khoa: "INELIGIBLE", nhan: "Bị hoãn" },
];

const NHAN_TONG: Record<ContentQueueOverall, string> = {
  PENDING: "Chờ chạy", RUNNING: "Đang chạy", FAILED: "Lỗi",
  COMPLETE: "Hoàn tất", INELIGIBLE: "Bị hoãn",
};

const LOP_TONG: Record<ContentQueueOverall, string> = {
  PENDING: "tt-cho", RUNNING: "tt-treo", FAILED: "tt-tuchoi",
  COMPLETE: "tt-duyet", INELIGIBLE: "tt-trong",
};

const KY_HIEU: Record<ContentQueueStageState, string> = {
  PENDING: "·", RUNNING: "▶", DONE: "✓", SKIPPED: "—", FAILED: "✕",
};

const LOP_O: Record<ContentQueueStageState, string> = {
  PENDING: "cq-o", RUNNING: "cq-o cq-o-chay", DONE: "cq-o cq-o-xong",
  SKIPPED: "cq-o cq-o-bo", FAILED: "cq-o cq-o-loi",
};

/** Chi cong doan `FAILED`/`RUNNING` xep lai duoc — server tu choi 409 voi
    `DONE` (lam lai viec da xong) va `SKIPPED` (quyet dinh chinh sach). Giao
    dien chi hien nut cho dung nhung cai server se nhan, chu khong "bam roi
    bao loi". */
function xepLaiDuoc(row: ContentQueueRow, stage: ContentQueueStage): boolean {
  if (row.ineligible) return false;
  if (stage === "render" && row.rights_mode !== "REHOST_ALLOWED") return false;
  const s = row.stages[stage];
  return s === "FAILED" || s === "RUNNING";
}

/** So cong doan da ket thuc / tong — thanh tien do khong can truong moi nao. */
function tienDo(row: ContentQueueRow): string {
  const states = STAGES.map((s) => row.stages[s.khoa]);
  const xong = states.filter((s) => s === "DONE" || s === "SKIPPED").length;
  return `${xong}/${states.length}`;
}

/** `last_error` mang tien to ten cong doan va, khi dang doi, `CHO:`. Bo tien
    to cho de doc — thong tin khong mat vi nhan phia truoc da noi ro day la
    loi, dang cho, hay bi hoan. */
function lyDoNgan(row: ContentQueueRow): string {
  if (!row.last_error) return "";
  return row.last_error
    .replace(/^INELIGIBLE:\s*/, "")
    .replace(/^\w+:\s*(CHO:\s*)?/, "");
}

export default function TrangHangDoiNoiDung() {
  const [loc, setLoc] = useState<"" | ContentQueueOverall>("");
  const [dangXepLai, setDangXepLai] = useState("");
  const toast = useToast();

  const napDanhSach = useCallback(() => adminApi.contentQueue(loc, 100, 0), [loc]);
  const danhSach = useAsyncData<ContentQueueList>(napDanhSach);

  const napTongHop = useCallback(() => adminApi.contentQueueSummary(), []);
  const tongHop = useAsyncData<ContentQueueSummary>(napTongHop);

  const xepLai = useCallback(
    async (itemId: string, stage: ContentQueueStage) => {
      setDangXepLai(`${itemId}:${stage}`);
      try {
        await adminApi.contentQueueRequeue(itemId, stage);
        toast.ok(
          "Đã xếp lại. Tiến trình xử lý sẽ nhặt nó ở lần quét kế tiếp — " +
            "trang này không tự chạy việc.",
        );
        danhSach.reload();
        tongHop.reload();
      } catch (cause) {
        toast.error(loiApi(cause, "Không xếp lại được công đoạn này."));
      } finally {
        setDangXepLai("");
      }
    },
    [danhSach, tongHop, toast],
  );

  const ds = danhSach.data?.items ?? [];
  const tong = tongHop.data;

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconInbox size={19} /> Hàng đợi sản xuất nội dung
      </h2>
      <p className="hint">
        Trang này <strong>xếp việc</strong>, không chạy việc. Tiến trình xử lý
        chạy riêng và <strong>chỉ một bản duy nhất</strong>; xếp lại một công
        đoạn chỉ đưa nó về &ldquo;chờ chạy&rdquo;.
      </p>

      {tong ? (
        <div className="row row-tight" style={{ flexWrap: "wrap" }}>
          {(Object.keys(NHAN_TONG) as ContentQueueOverall[]).map((k) => (
            <button
              key={k}
              type="button"
              className={`cq-the ${loc === k ? "cq-the-chon" : ""}`}
              aria-pressed={loc === k}
              onClick={() => setLoc(loc === k ? "" : k)}
            >
              <span className="cq-the-so">{tong.by_overall[k] ?? 0}</span>
              <span className="hint">{NHAN_TONG[k]}</span>
            </button>
          ))}
          <div className="cq-the">
            <span className="cq-the-so">{tong.total}</span>
            <span className="hint">Tổng</span>
          </div>
        </div>
      ) : null}

      <div className="seg" role="group" aria-label="Lọc theo trạng thái"
           style={{ flexWrap: "wrap" }}>
        {BO_LOC.map((t) => (
          <button key={t.khoa || "all"} type="button" className="seg-item"
                  aria-pressed={loc === t.khoa}
                  onClick={() => setLoc(t.khoa)}>
            {t.nhan}
          </button>
        ))}
      </div>

      <DanhSachTrangThai dangTai={danhSach.loading} loi={danhSach.error}
                         rong={ds.length === 0} onThuLai={danhSach.reload}>
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <thead>
              <tr>
                <th scope="col">Mục</th>
                <th scope="col">Công đoạn</th>
                <th scope="col">Trạng thái</th>
                <th scope="col">Kết quả</th>
                <th scope="col">Hành động</th>
              </tr>
            </thead>
            <tbody>
              {ds.map((row) => (
                <tr key={row.item_id}>
                  <td>
                    <Link href={`/admin/content-queue/${encodeURIComponent(row.item_id)}`}>
                      {row.title || row.item_id}
                    </Link>
                    <div className="hint">
                      {row.source_id} · {row.rights_mode}
                      {row.has_transcript_checkpoint ? " · có điểm dừng" : ""}
                      {row.attempts > 0 ? ` · ${row.attempts} lỗi liên tiếp` : ""}
                    </div>
                  </td>
                  <td>
                    <div className="row row-tight" aria-label="Tiến độ công đoạn">
                      {STAGES.map((s) => (
                        <span key={s.khoa} className={LOP_O[row.stages[s.khoa]]}
                              title={`${s.nhan}: ${row.stages[s.khoa]}`}>
                          {KY_HIEU[row.stages[s.khoa]]}
                        </span>
                      ))}
                      <span className="hint mono">{tienDo(row)}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`tt ${LOP_TONG[row.overall]}`}>
                      {NHAN_TONG[row.overall]}
                    </span>
                    {row.last_error ? (
                      <div className="hint">
                        {row.ineligible ? "Bị hoãn: "
                          : row.waiting ? "Đang chờ: " : "Lỗi: "}
                        {lyDoNgan(row)}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    {row.novel_id ? (
                      <Link href={`/fanfic/${row.novel_id}`}>Bản nháp</Link>
                    ) : (
                      <span className="hint">—</span>
                    )}
                    {row.source_url ? (
                      <div className="hint">
                        <a href={row.source_url} target="_blank" rel="noreferrer">
                          Nguồn gốc
                        </a>
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <div className="row row-tight" style={{ flexWrap: "wrap" }}>
                      {STAGES.filter((s) => xepLaiDuoc(row, s.khoa)).map((s) => (
                        <button key={s.khoa} type="button" className="btn btn-sm btn-ghost"
                                disabled={dangXepLai === `${row.item_id}:${s.khoa}`}
                                onClick={() => xepLai(row.item_id, s.khoa)}>
                          {dangXepLai === `${row.item_id}:${s.khoa}`
                            ? "Đang xếp…"
                            : `Xếp lại ${s.nhan.toLowerCase()}`}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DanhSachTrangThai>
    </section>
  );
}
