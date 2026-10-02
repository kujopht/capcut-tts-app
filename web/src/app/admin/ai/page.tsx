"use client";

/**
 * /admin/ai — AI Control Plane (docs/ai/AI_ADMIN_CONTROL_PLANE.md).
 *
 * Đọc: ADMIN hoặc OWNER. Ghi: CHỈ OWNER — server là người quyết (403), giao
 * diện chỉ ẩn/khoá nút để không hứa một hành động sẽ bị từ chối.
 *
 * Trang này KHÔNG BAO GIỜ thấy khoá API: server chỉ trả `secret_ref`, tên
 * biến môi trường, có/thiếu và vân tay `sha256:xxxxxxxx`. Không có ô nào để
 * nhập khoá — khoá thật đặt ở biến môi trường `FAS_AI_SECRET_<secret_ref>`
 * trên máy chủ.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  AiAdminApiError,
  aiControl,
  type AiAuditItem,
  type AiConfig,
  type AiGlobalPatch,
  type AiOverview,
  type AiPresetName,
  type AiProviderType,
  type AiSlotInput,
} from "@/lib/admin/aiControl";
import { Loading } from "@/components/ui";
import { IconBulb } from "@/components/Icons";
import { AiOverviewCards, ngayUtc } from "@/components/admin/ai/AiOverviewCards";
import { AiKillSwitch } from "@/components/admin/ai/AiKillSwitch";
import { AiProviderTypes } from "@/components/admin/ai/AiProviderTypes";
import { AiSlotList } from "@/components/admin/ai/AiSlotList";
import { AiRoutingProfiles } from "@/components/admin/ai/AiRoutingProfiles";
import { AiGlobalCaps } from "@/components/admin/ai/AiGlobalCaps";
import { AiRolloutPresets } from "@/components/admin/ai/AiRolloutPresets";
import { AiAuditTable } from "@/components/admin/ai/AiAuditTable";

type LoiTruong = { field: string; message: string }[];
type DuLieu = { overview: AiOverview; config: AiConfig; audit: AiAuditItem[] };
/** Nơi hiện lỗi 422 của một lần lưu — cạnh đúng form đã gửi. */
type NoiLoi = { loai: "slot" } | { loai: "global" } | { loai: "hoso"; ten: string } | { loai: "chung" };

const MUC = [
  ["tong-quan", "Tổng quan"],
  ["cong-tac", "Công tắc"],
  ["providers", "Providers"],
  ["dinh-tuyen", "Định tuyến"],
  ["han-muc", "Hạn mức"],
  ["nhat-ky", "Nhật ký"],
] as const;

async function taiDuLieu(): Promise<DuLieu> {
  const [overview, config, audit] = await Promise.all([
    aiControl.getOverview(),
    aiControl.getConfig(),
    aiControl.getAudit(50),
  ]);
  return { overview, config, audit: audit.items };
}

export default function AdminAi() {
  const { profile } = useSession();
  const laOwner = profile?.admin_role === "owner";

  const [duLieu, setDuLieu] = useState<DuLieu | null>(null);
  const [dangTai, setDangTai] = useState(true);
  const [loiTai, setLoiTai] = useState<ApiError | null>(null);
  const [dangGui, setDangGui] = useState(false);
  const [thongBao, setThongBao] = useState("");
  const [loiChung, setLoiChung] = useState("");
  const [loiSlot, setLoiSlot] = useState<LoiTruong>([]);
  const [loiGlobal, setLoiGlobal] = useState<LoiTruong>([]);
  const [loiHoSo, setLoiHoSo] = useState<Record<string, LoiTruong>>({});

  const [taiLuc, setTaiLuc] = useState(0);

  const nhan = useCallback((d: DuLieu) => {
    setDuLieu(d);
    setTaiLuc(Date.now());
    setLoiTai(null);
  }, []);
  const hong = useCallback((e: unknown) => {
    setLoiTai(e instanceof ApiError ? e : new ApiError("Không tải được bảng điều khiển AI.", 0));
  }, []);

  // Tải lần đầu: setState chỉ trong callback của promise (không đồng bộ
  // trong thân effect), và bỏ kết quả nếu trang đã rời đi.
  useEffect(() => {
    let conSong = true;
    taiDuLieu()
      .then((d) => { if (conSong) nhan(d); })
      .catch((e) => { if (conSong) hong(e); })
      .finally(() => { if (conSong) setDangTai(false); });
    return () => { conSong = false; };
  }, [nhan, hong]);

  const nap = useCallback(async () => {
    try {
      nhan(await taiDuLieu());
    } catch (e) {
      hong(e);
    } finally {
      setDangTai(false);
    }
  }, [nhan, hong]);

  /** Chạy MỘT thao tác ghi: khoá nút, xoá lỗi cũ, tải lại sau khi xong.
   *  Trả `true` khi thành công để form tự đóng. */
  const chay = useCallback(
    async (fn: () => Promise<unknown>, noi: NoiLoi, xong: string): Promise<boolean> => {
      setDangGui(true);
      setThongBao("");
      setLoiChung("");
      setLoiSlot([]);
      setLoiGlobal([]);
      setLoiHoSo({});
      try {
        await fn();
        setThongBao(`${xong} Có hiệu lực trên mọi máy chủ trong ≤15 giây.`);
        await nap();
        return true;
      } catch (e) {
        const loi = e instanceof AiAdminApiError ? e.fieldErrors : [];
        if (e instanceof ApiError && e.status === 422 && loi.length) {
          if (noi.loai === "slot") setLoiSlot(loi);
          else if (noi.loai === "global") setLoiGlobal(loi);
          else if (noi.loai === "hoso") setLoiHoSo({ [noi.ten]: loi });
          setLoiChung("Dữ liệu chưa hợp lệ — xem lỗi cạnh từng trường.");
        } else if (e instanceof ApiError && e.status === 409) {
          setLoiChung(`${e.message} Đã tải lại cấu hình mới nhất — kiểm tra rồi thử lại.`);
          await nap();
        } else if (e instanceof ApiError && e.status === 403) {
          setLoiChung("Chỉ OWNER mới thay đổi được cấu hình AI.");
        } else {
          setLoiChung(e instanceof ApiError ? e.message : "Không lưu được — thử lại.");
        }
        return false;
      } finally {
        setDangGui(false);
      }
    },
    [nap],
  );

  if (dangTai) return <Loading />;

  if (loiTai || !duLieu) {
    const chuaBat = loiTai?.code === "ai_admin_not_enabled";
    const khongQuyen = loiTai?.status === 403;
    return (
      <section className="stack">
        <TieuDe />
        <div className="card admin-chua-cau-hinh stack-2" role={chuaBat ? "status" : "alert"}>
          <strong>
            {chuaBat
              ? "Bảng điều khiển AI chưa được bật trên máy chủ này."
              : khongQuyen
                ? "Chỉ ADMIN hoặc OWNER xem được bảng điều khiển AI."
                : "Không tải được bảng điều khiển AI."}
          </strong>
          <p className="hint">
            {chuaBat
              ? "Cờ FAS_AI_ADMIN_V1 đang tắt — Trợ lý AI vẫn chạy theo cấu hình cũ (hoặc tắt). Owner bật cờ trên máy chủ sau khi đã áp schema và đặt khoá."
              : khongQuyen
                ? "Tài khoản này có quyền quản trị nhưng không đủ vai trò cho mục này."
                : loiTai?.message}
          </p>
          {!chuaBat && !khongQuyen ? (
            <div className="row">
              <button type="button" className="btn btn-sm" onClick={() => { setDangTai(true); void nap(); }}>
                Thử lại
              </button>
            </div>
          ) : null}
        </div>
      </section>
    );
  }

  const { overview, config, audit } = duLieu;
  const c = config.controls;

  return (
    <section className="stack">
      <div className="row row-spread">
        <TieuDe />
        <button type="button" className="btn btn-sm" disabled={dangGui} onClick={() => void nap()}>
          Làm mới
        </button>
      </div>

      <nav className="ai-admin-tab" aria-label="Các mục của AI Control Plane">
        {MUC.map(([id, nhan]) => <a key={id} href={`#${id}`}>{nhan}</a>)}
      </nav>

      {!laOwner ? (
        <div className="card admin-chua-cau-hinh" role="status">
          <strong>Chế độ chỉ đọc.</strong>{" "}
          <span className="hint">Bạn đang xem với vai trò {profile?.admin_role?.toUpperCase() ?? "—"}; chỉ OWNER mới thay đổi được cấu hình AI.</span>
        </div>
      ) : null}

      <div aria-live="polite" className="stack-2">
        {thongBao ? <div className="card ai-admin-thong-bao" role="status">{thongBao}</div> : null}
        {loiChung ? <div className="card ai-admin-xac-nhan" role="alert">{loiChung}</div> : null}
      </div>

      <section id="tong-quan" className="stack-2 ai-admin-muc">
        <h2 className="section-title">Tổng quan hôm nay ({ngayUtc(overview.day)}, UTC)</h2>
        <AiOverviewCards overview={overview} config={config} />
      </section>

      <section id="cong-tac" className="stack-2 ai-admin-muc">
        <h2 className="section-title">Công tắc</h2>
        <AiKillSwitch
          aiEnabled={c.ai_enabled}
          laOwner={laOwner}
          dangGui={dangGui}
          onDoi={(bat) => void chay(
            () => aiControl.updateGlobal({ ai_enabled: bat, expected_version: c.version }),
            { loai: "chung" },
            bat ? "Đã BẬT AI." : "Đã TẮT toàn bộ AI.",
          )}
        />
        <AiProviderTypes
          providerTypes={config.provider_types}
          trangThai={c.provider_types}
          laOwner={laOwner}
          onDoi={async (type: AiProviderType, enabled: boolean) => {
            await chay(() => aiControl.setProviderType(type, enabled, c.version), { loai: "chung" },
              `${enabled ? "Đã bật" : "Đã tắt"} loại provider ${type}.`);
          }}
        />
      </section>

      <section id="providers" className="stack-2 ai-admin-muc">
        <h2 className="section-title">Providers &amp; slot</h2>
        <p className="hint">
          Mỗi slot trỏ tới MỘT khoá qua tên tham chiếu — nhiều project cùng một loại là nhiều
          slot trong cùng pool (<code>&lt;LOẠI&gt;_PROJECT_01</code>, <code>&lt;LOẠI&gt;_PROJECT_02</code>…).
          Cooldown, hạn mức và sức khoẻ tính riêng từng slot.
        </p>
        <AiSlotList
          slots={config.slots}
          meta={config.meta}
          nhanLoai={Object.fromEntries(config.provider_types.map((t) => [t.type, t.label]))}
          taiLuc={taiLuc}
          laOwner={laOwner}
          dangGui={dangGui}
          loiTruong={loiSlot}
          onTao={(p: AiSlotInput) => chay(() => aiControl.createSlot(p), { loai: "slot" }, `Đã tạo slot ${p.slot_id}.`)}
          onSua={(id, p) => chay(() => aiControl.updateSlot(id, p), { loai: "slot" }, `Đã lưu slot ${id}.`)}
          onXoa={(id) => chay(() => aiControl.deleteSlot(id), { loai: "chung" }, `Đã xoá slot ${id}.`)}
          onResetCooldown={(id) => chay(() => aiControl.resetCooldown(id), { loai: "chung" }, `Đã reset cooldown ${id}.`)}
          onKiemTra={async (id) => {
            let ketQua = "";
            const ok = await chay(async () => {
              const { probe } = await aiControl.probeSlot(id);
              ketQua = probe.ok
                ? `OK · ${probe.latency_ms} ms${probe.ttft_ms != null ? ` (TTFT ${probe.ttft_ms} ms)` : ""} · ${probe.model}`
                : `${probe.code ?? "lỗi"}${probe.category ? ` · ${probe.category}` : ""}`;
            }, { loai: "chung" }, "");
            if (ok) setThongBao(`Kiểm tra ${id}: ${ketQua}`);
            return ok;
          }}
        />
      </section>

      <section id="dinh-tuyen" className="stack-2 ai-admin-muc">
        <h2 className="section-title">Hồ sơ định tuyến</h2>
        <p className="hint">
          Thứ tự bước = thứ tự thử. Mỗi lượt thử mỗi slot tối đa MỘT lần và chỉ chuyển slot
          trước token đầu tiên; hết slot đủ điều kiện thì người dùng nhận lỗi thân thiện.
        </p>
        <AiRoutingProfiles
          profiles={config.profiles}
          modeProfiles={c.mode_profiles}
          webSearchProfile={c.web_search_profile}
          meta={config.meta}
          types={config.provider_types}
          slots={config.slots}
          laOwner={laOwner}
          dangGui={dangGui}
          loiTheoHoSo={loiHoSo}
          onLuu={(ten, steps, enabled) =>
            chay(() => aiControl.updateProfile(ten, { steps, enabled }), { loai: "hoso", ten }, `Đã lưu hồ sơ ${ten}.`)}
        />
      </section>

      <section id="han-muc" className="stack-2 ai-admin-muc">
        <h2 className="section-title">Hạn mức &amp; chế độ</h2>
        {config.rollout ? (
          <AiRolloutPresets
            rollout={config.rollout}
            laOwner={laOwner}
            dangGui={dangGui}
            onApDung={(name: AiPresetName) =>
              chay(() => aiControl.applyPreset(name, c.version), { loai: "global" }, `Đã áp preset ${name}.`)}
          />
        ) : null}
        {/* `key` theo phiên bản: người khác vừa lưu (hoặc ta vừa lưu) thì form
            dựng lại từ giá trị mới — không cần effect sao chép prop vào state. */}
        <AiGlobalCaps
          key={c.version}
          controls={c}
          profiles={config.meta.profiles}
          modes={config.meta.modes}
          laOwner={laOwner}
          dangGui={dangGui}
          loiTruong={loiGlobal}
          onLuu={(patch: AiGlobalPatch) => chay(() => aiControl.updateGlobal(patch), { loai: "global" }, "Đã lưu hạn mức.")}
        />
      </section>

      <section id="nhat-ky" className="stack-2 ai-admin-muc">
        <h2 className="section-title">Nhật ký thay đổi (50 gần nhất)</h2>
        <AiAuditTable items={audit} />
      </section>
    </section>
  );
}

function TieuDe() {
  return (
    <h2 className="section-title section-title-icon">
      <IconBulb size={19} /> AI Control Plane
    </h2>
  );
}
