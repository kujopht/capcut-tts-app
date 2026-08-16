"use client";

/**
 * AI / Credits — Admin Control Center V2, Phase 2.
 *
 * Chi tieu Image Studio (Shared Premium) + cong tac khan cap. Cong tac CHI
 * OWNER bam duoc — server tu choi ADMIN/MODERATOR bang 403 (xem
 * `owner_profile` o server/main.py); nut o day tu vo hieu hoa khi khong phai
 * OWNER de khong hua mot hanh dong se bi tu choi.
 */

import { useCallback, useState } from "react";
import {
  adminApi,
  type AdminImageStudioSpending,
  type AdminOverview,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { DanhSachTrangThai, OSo } from "@/components/AdminShell";
import { IconSparkles } from "@/components/Icons";

export default function AdminAiCredits() {
  const { profile } = useSession();
  const toast = useToast();
  const laOwner = profile?.admin_role === "owner";

  const napChiTieu = useCallback(() => adminApi.imageStudioSpending(), []);
  const { data, loading, error, reload } =
    useAsyncData<AdminImageStudioSpending>(napChiTieu);
  const napTongQuan = useCallback(() => adminApi.overview(), []);
  const { data: tongQuan } = useAsyncData<AdminOverview>(napTongQuan);

  const [dangGui, setDangGui] = useState(false);

  const doiCongTac = async (engaged: boolean) => {
    setDangGui(true);
    try {
      await adminApi.imageStudioKillSwitch(engaged);
      toast.ok(engaged ? "Đã bật công tắc khẩn cấp." : "Đã tắt công tắc khẩn cấp.");
      reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Không thực hiện được.");
    } finally {
      setDangGui(false);
    }
  };

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconSparkles size={19} /> AI / Credits
      </h2>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!data} onThuLai={reload}>
        {data ? (
          <div className="stack-3">
            <div className="stat-grid admin-luoi">
              <OSo
                nhan="Chi tiêu tháng (USD)"
                so={Math.round(data.spent_usd * 100) / 100}
                ghi_chu={`Ngân sách: $${data.budget_usd} · Cảnh báo: $${data.warning_usd}`}
              />
              <OSo nhan="Đang chạy đồng thời" so={data.active_concurrent}
                ghi_chu={`Tối đa: ${data.max_concurrent}`} />
              <OSo nhan="Dự án dịch" so={tongQuan?.product.translation_projects_total ?? null} />
              <OSo nhan="Job TTS" so={tongQuan?.product.tts_jobs_total ?? null} />
            </div>

            <div className="card stack-2">
              <strong>Công tắc khẩn cấp Shared Premium</strong>
              <p className="hint">
                Trạng thái hiện tại:{" "}
                <span className={`tt ${data.kill_switch_engaged ? "tt-treo" : "tt-duyet"}`}>
                  {data.kill_switch_engaged ? "ĐANG TẮT sinh ảnh" : "Bình thường"}
                </span>
                . Không ảnh hưởng Quick Free/BYOP, chỉ Shared Premium.
              </p>
              {!laOwner ? (
                <p className="hint" role="alert">
                  Chỉ Owner mới đổi được công tắc này.
                </p>
              ) : null}
              <div className="row row-tight">
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={!laOwner || dangGui || data.kill_switch_engaged}
                  onClick={() => doiCongTac(true)}
                >
                  Bật công tắc khẩn cấp (tắt sinh ảnh)
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={!laOwner || dangGui || !data.kill_switch_engaged}
                  onClick={() => doiCongTac(false)}
                >
                  Tắt công tắc, cho phép lại
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
