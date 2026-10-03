"use client";

/**
 * Danh sách slot, gộp theo loại provider. Đếm ngược cooldown chạy client-side
 * (mỗi giây, chỉ khi có slot đang COOLDOWN — không polling mạng, không chạy
 * khi tab không có slot nào cần đếm). Thời gian còn lại TÍNH từ mốc tải
 * (`taiLuc`) chứ không chép `cooldown_s` vào state — dữ liệu mới về là số
 * đúng ngay, không cần effect đồng bộ.
 */

import { useEffect, useState } from "react";
import type { AiConfigMeta, AiProviderType, AiSlot, AiSlotInput } from "@/lib/admin/aiControl";
import {
  coThongTinHanMuc, hostCuaEndpoint, moTaDoTre, moTaHanDung, moTaKhoaChan, moTaUocTinh, nhanHanMuc, nhanThinking,
} from "@/lib/admin/aiSlotView";
import { AiQuotaBar } from "./AiQuotaBar";
import { AiSlotForm } from "./AiSlotForm";

const NHAN_TRANG_THAI: Record<AiSlot["health"]["status"], string> = {
  HEALTHY: "HEALTHY",
  COOLDOWN: "COOLDOWN",
  DISABLED: "DISABLED",
  MISSING_SECRET: "THIẾU KHOÁ",
  OVER_CAP: "OVER_CAP",
  DEGRADED: "DEGRADED",
  GATE_CLOSED: "CHƯA BẬT Ở MÁY CHỦ",
  QUOTA_EXHAUSTED: "NCC BÁO HẾT HẠN MỨC",
  META_CORRUPT: "DỮ LIỆU SLOT HỎNG",
};

const LOP_TRANG_THAI: Record<AiSlot["health"]["status"], string> = {
  HEALTHY: "tt-duyet",
  COOLDOWN: "tt-cho",
  DISABLED: "tt-trong",
  MISSING_SECRET: "tt-tuchoi",
  OVER_CAP: "tt-tuchoi",
  DEGRADED: "tt-treo",
  GATE_CLOSED: "tt-cho",
  QUOTA_EXHAUSTED: "tt-tuchoi",
  META_CORRUPT: "tt-tuchoi",
};

function thoiGianTuongDoi(iso: string | null): string {
  if (!iso) return "chưa có";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const giay = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (giay < 60) return `${giay} giây trước`;
  const phut = Math.round(giay / 60);
  if (phut < 60) return `${phut} phút trước`;
  const gio = Math.round(phut / 60);
  if (gio < 24) return `${gio} giờ trước`;
  return `${Math.round(gio / 24)} ngày trước`;
}

function useDemNguoc(slots: AiSlot[], taiLuc: number): Record<string, number> {
  const coCooldown = slots.some((s) => s.health.status === "COOLDOWN" && s.health.cooldown_s > 0);
  const [bayGio, setBayGio] = useState(taiLuc);

  useEffect(() => {
    if (!coCooldown) return;
    const id = window.setInterval(() => setBayGio(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [coCooldown]);

  const daQua = Math.max(0, (bayGio - taiLuc) / 1000);
  return Object.fromEntries(
    slots.map((s) => [s.slot_id, Math.max(0, Math.round(s.health.cooldown_s - daQua))]),
  );
}

function DongSlot({
  slot,
  con,
  laOwner,
  dangGui,
  onSua,
  onResetCooldown,
  onKiemTra,
  onXoa,
}: {
  slot: AiSlot;
  con: number;
  laOwner: boolean;
  dangGui: boolean;
  onSua: () => void;
  onResetCooldown: () => void;
  onKiemTra: () => void;
  onXoa: () => void;
}) {
  const [xacNhanXoa, setXacNhanXoa] = useState(false);
  const h = slot.health;

  return (
    <div className="card stack-2 ai-admin-slot">
      <div className="row row-spread">
        <strong>{slot.label} <span className="hint">({slot.slot_id})</span></strong>
        <span className={`tt ${LOP_TRANG_THAI[h.status]}`}>
          {h.status === "COOLDOWN"
            ? `COOLDOWN · 429×${h.recent_429} · ${con}s`
            : NHAN_TRANG_THAI[h.status]}
        </span>
      </div>

      <dl className="admin-ho-so">
        <dt>Model</dt><dd>{slot.model}</dd>
        <dt>Endpoint</dt><dd><code>{hostCuaEndpoint(slot.effective_endpoint)}</code></dd>
        <dt>Bật</dt><dd>{slot.enabled ? "Có" : "Không"}</dd>
        {h.gate ? (
          <>
            <dt>Cổng máy chủ</dt>
            <dd>
              <code>{h.gate.env}</code>{" "}
              <span className={`tt ${h.gate.open ? "tt-duyet" : "tt-tuchoi"}`}>
                {h.gate.open ? "Đang mở" : "ĐÓNG — không có request nào tới nhà cung cấp"}
              </span>
            </dd>
          </>
        ) : null}
        <dt>Tầng năng lực</dt>
        <dd>{slot.tiers && slot.tiers.length ? slot.tiers.join(", ") : "chưa phân loại"}</dd>
        {slot.thinking && slot.thinking !== "provider_default" ? (
          <>
            <dt>Thinking</dt>
            <dd>{nhanThinking(slot.thinking)}</dd>
          </>
        ) : null}
        <dt>Độ trễ</dt><dd>{moTaDoTre(h.latency)}</dd>
        {coThongTinHanMuc(h.quota) && h.quota ? (
          <>
            <dt>Hạn mức miễn phí</dt>
            <dd>
              <span className={`tt ${nhanHanMuc(h.quota).lop}`}>{nhanHanMuc(h.quota).nhan}</span>
              {h.quota.remaining !== null ? ` · số Owner nhập ${h.quota.remaining.toLocaleString("vi-VN")} token` : ""}
              {moTaUocTinh(h.quota) ? ` · ${moTaUocTinh(h.quota)}` : ""}
              {h.quota.expires_at ? ` · hết hạn ${new Date(h.quota.expires_at).toLocaleString("vi-VN")} (${moTaHanDung(h.quota)})` : ""}
              {h.quota.only ? <span className="tt tt-cho"> chỉ dùng hạn mức miễn phí</span> : null}
              {moTaKhoaChan(h.quota) ? (
                <span className="tt tt-tuchoi"> khoá đang CHẶN slot: {moTaKhoaChan(h.quota)}</span>
              ) : null}
              {h.quota.provider_exhausted_today ? <span className="tt tt-tuchoi"> nhà cung cấp báo hết hôm nay</span> : null}
              <span className="hint">
                {" · "}số Owner nhập {thoiGianTuongDoi(h.quota.updated_at)} — không tự cập nhật, cập nhật lại từ trang nhà cung cấp
              </span>
            </dd>
          </>
        ) : null}
        {h.meta_corrupt ? (
          <>
            <dt>Dữ liệu slot</dt>
            <dd><span className="tt tt-tuchoi">Siêu dữ liệu trong kho hỏng — Sửa rồi Lưu để ghi đè</span></dd>
          </>
        ) : null}
        <dt>Ưu tiên / trọng số</dt><dd>{slot.priority} / {slot.weight}</dd>
        <dt>Thất bại liên tiếp</dt><dd>{h.consecutive_failures}</dd>
        <dt>Lần thành công gần nhất</dt><dd>{thoiGianTuongDoi(h.last_success_at)}</dd>
        <dt>Lỗi gần nhất</dt>
        <dd>
          {h.last_error_code ? (
            <>
              <code>{h.last_error_code}</code>
              {h.last_error_category ? <> · <code>{h.last_error_category}</code></> : null}
              <span className="hint"> · {thoiGianTuongDoi(h.last_error_at ?? null)}</span>
            </>
          ) : "chưa có"}
        </dd>
        <dt>Kiểm hôm nay</dt>
        <dd>
          {h.probes_today ? `${h.probes_today.count}/${h.probes_today.cap} (đạt ${h.probes_today.ok})` : "—"}
          {h.probe_stable ? <span className="tt tt-duyet"> ổn định</span> : null}
          {h.probe_history && h.probe_history.length ? (
            <span className="hint">
              {" · "}
              {h.probe_history.map((p) => (p.ok ? `ok ${p.latency_ms ?? "?"}ms` : (p.code ?? "lỗi"))).join(" → ")}
            </span>
          ) : null}
          <span className="hint"> · không trừ hạn mức người dùng</span>
        </dd>
        <dt>Workload</dt><dd>{slot.workloads.length ? slot.workloads.join(", ") : "—"}</dd>
        <dt>Secret ref</dt>
        <dd>
          {h.secret.ref} → <code>{h.secret.env_name}</code>{" "}
          <span className={`tt ${h.secret.present ? "tt-duyet" : "tt-tuchoi"}`}>
            {h.secret.present ? "Đã cấu hình" : "Thiếu khoá"}
          </span>
          {h.secret.present ? <span className="hint"> · {h.secret.fingerprint}</span> : null}
        </dd>
      </dl>

      <AiQuotaBar nhan="Yêu cầu hôm nay" daDung={h.usage_today.requests} tran={slot.daily_request_cap} />
      <AiQuotaBar nhan="Token hôm nay" daDung={h.usage_today.input_tokens + h.usage_today.output_tokens} tran={slot.daily_token_cap} />
      <p className="hint">
        RPM mềm: {slot.rpm_soft_cap || "không giới hạn"} · TPM mềm: {slot.tpm_soft_cap || "không giới hạn"} ·
        Chi phí hôm nay: ${(h.usage_today.cost_micro_usd / 1_000_000).toFixed(4)}
      </p>

      {laOwner ? (
        xacNhanXoa ? (
          <div className="row row-tight">
            <span className="hint">Xoá hẳn slot {slot.slot_id}?</span>
            <button type="button" className="btn btn-danger btn-sm" disabled={dangGui} onClick={onXoa}>
              Xác nhận xoá
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setXacNhanXoa(false)}>Huỷ</button>
          </div>
        ) : (
          <div className="row row-tight">
            <button type="button" className="btn btn-sm" onClick={onSua} disabled={dangGui}>Sửa</button>
            <button type="button" className="btn btn-sm" onClick={onKiemTra}
                    disabled={dangGui || !h.secret.present || (!!h.gate && !h.gate.open)}
                    title={h.gate && !h.gate.open
                      ? `Cổng máy chủ đang đóng: đặt biến môi trường ${h.gate.env}=1 rồi khởi động lại dịch vụ`
                      : "Gửi MỘT request tối thiểu thật qua slot này (chạy được cả khi slot đang tắt)"}>
              Kiểm tra
            </button>
            {h.status === "COOLDOWN" ? (
              <button type="button" className="btn btn-sm" onClick={onResetCooldown} disabled={dangGui}>
                Reset cooldown
              </button>
            ) : null}
            <button type="button" className="btn btn-danger btn-sm" onClick={() => setXacNhanXoa(true)} disabled={dangGui}>
              Xoá
            </button>
          </div>
        )
      ) : null}
    </div>
  );
}

export function AiSlotList({
  slots,
  meta,
  nhanLoai,
  taiLuc,
  laOwner,
  dangGui,
  loiTruong,
  onTao,
  onSua,
  onXoa,
  onResetCooldown,
  onKiemTra,
}: {
  slots: AiSlot[];
  meta: AiConfigMeta;
  /** Nhãn theo loại, từ `config.provider_types` — không viết cứng tên provider. */
  nhanLoai: Record<string, string>;
  /** `Date.now()` lúc dữ liệu về — mốc cho đếm ngược cooldown. */
  taiLuc: number;
  laOwner: boolean;
  dangGui: boolean;
  loiTruong: { field: string; message: string }[];
  /** Trả `true` khi thành công — danh sách tự đóng form/reset trạng thái. */
  onTao: (payload: AiSlotInput) => Promise<boolean>;
  onSua: (slotId: string, payload: AiSlotInput) => Promise<boolean>;
  onXoa: (slotId: string) => Promise<boolean>;
  onResetCooldown: (slotId: string) => Promise<boolean>;
  onKiemTra: (slotId: string) => Promise<boolean>;
}) {
  const [dangSua, setDangSua] = useState<string | null>(null);
  const [dangTao, setDangTao] = useState(false);
  const dem = useDemNguoc(slots, taiLuc);

  const theoLoai = new Map<AiProviderType, AiSlot[]>();
  for (const s of slots) {
    theoLoai.set(s.provider_type, [...(theoLoai.get(s.provider_type) ?? []), s]);
  }

  if (slots.length === 0 && !dangTao) {
    return (
      <div className="card admin-chua-cau-hinh stack-2" role="status">
        <strong>Chưa có slot provider nào.</strong>
        <p className="hint">
          Thêm một slot để bắt đầu định tuyến AI qua provider đó. Khoá thật
          KHÔNG nhập ở đây — sau khi tạo slot với một `secret_ref`, chủ máy
          chủ cần đặt biến môi trường <code>FAS_AI_SECRET_&lt;secret_ref&gt;</code>{" "}
          rồi khởi động lại dịch vụ để slot chuyển từ &quot;Thiếu khoá&quot;
          sang &quot;Đã cấu hình&quot;.
        </p>
        {laOwner ? (
          <button type="button" className="btn btn-primary" onClick={() => setDangTao(true)}>
            Thêm slot
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="stack-3">
      {laOwner && !dangTao ? (
        <div className="row">
          <button type="button" className="btn btn-primary" onClick={() => setDangTao(true)}>
            Thêm slot
          </button>
        </div>
      ) : null}

      {dangTao ? (
        <AiSlotForm
          meta={meta}
          nhanLoai={nhanLoai}
          dangGui={dangGui}
          loiTruong={loiTruong}
          onLuu={(payload) => {
            void onTao(payload).then((ok) => { if (ok) setDangTao(false); });
          }}
          onHuy={() => setDangTao(false)}
        />
      ) : null}

      {[...theoLoai.entries()].map(([loai, dsSlot]) => (
        <div key={loai} className="stack-2">
          <h3 className="section-title-sm">{nhanLoai[loai] ?? loai} · pool {dsSlot.length} slot</h3>
          <div className="stack-2 ai-admin-slot-scroll">
            {dsSlot.map((s) =>
              dangSua === s.slot_id ? (
                <AiSlotForm
                  key={s.slot_id}
                  slot={s}
                  meta={meta}
                  nhanLoai={nhanLoai}
                  dangGui={dangGui}
                  loiTruong={loiTruong}
                  onLuu={(payload) => {
                    void onSua(s.slot_id, payload).then((ok) => { if (ok) setDangSua(null); });
                  }}
                  onHuy={() => setDangSua(null)}
                />
              ) : (
                <DongSlot
                  key={s.slot_id}
                  slot={s}
                  con={dem[s.slot_id] ?? s.health.cooldown_s}
                  laOwner={laOwner}
                  dangGui={dangGui}
                  onSua={() => setDangSua(s.slot_id)}
                  onResetCooldown={() => onResetCooldown(s.slot_id)}
                  onKiemTra={() => void onKiemTra(s.slot_id)}
                  onXoa={() => onXoa(s.slot_id)}
                />
              ),
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
