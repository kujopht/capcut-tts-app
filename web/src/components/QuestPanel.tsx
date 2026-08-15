"use client";

/**
 * Chuỗi ngày đọc + nhiệm vụ (ngày/tuần) CỦA CHÍNH MÌNH — V6 gamification.
 *
 * TÁCH RIÊNG khỏi `GamificationPanel` (cấp độ/danh xưng/vật phẩm) và
 * `AchievementGrid` (thành tựu) — ba module độc lập, ghép chung trong
 * `/account` qua thứ tự JSX, cùng khuôn mẫu đã có từ trước.
 *
 * Một lần tải cho cả chuỗi ngày đọc lẫn danh sách nhiệm vụ (`useAsyncData`
 * gọi cả hai `Promise.all`) — không polling, chỉ tải lại sau khi người dùng
 * chủ động bấm "Nhận thưởng".
 */

import { useCallback, useState } from "react";
import { api, type QuestItem } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { errorMessage } from "@/lib/session";
import { ProgressBar } from "@/components/ui";
import { IconFlame, IconScroll } from "@/components/Icons";

const TEN_KY: Record<QuestItem["period"], string> = {
  daily: "Hằng ngày",
  weekly: "Hằng tuần",
};

function TheNhiemVu({
  q,
  dangNhan,
  onNhan,
}: {
  q: QuestItem;
  dangNhan: boolean;
  onNhan: (key: string) => void;
}) {
  const phanTram =
    q.target_count > 0 ? Math.round((q.count / q.target_count) * 100) : 100;
  return (
    <div
      className={`quest-card do-hiem-${q.cosmetic_reward_key ? "rare" : "common"}`}
    >
      <span className="achievement-card-icon" aria-hidden="true">
        <IconScroll size={18} />
      </span>
      <div className="progress-card-body quest-card-body">
        <div className="row-between">
          <strong>{q.name}</strong>
          <span className="hint">{TEN_KY[q.period]}</span>
        </div>
        <span className="hint">{q.description}</span>
        <ProgressBar
          percent={phanTram}
          label={`Tiến độ ${q.name}: ${q.count}/${q.target_count}`}
        />
        <div className="row-between">
          <span className="hint achievement-card-progress">
            {q.count}/{q.target_count} · +{q.xp_reward} XP
            {q.cosmetic_reward_key ? " · kèm vật phẩm" : ""}
          </span>
          {q.claimed ? (
            <span className="badge badge-ok">Đã nhận</span>
          ) : q.completed ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onNhan(q.key)}
              disabled={dangNhan}
            >
              {dangNhan ? <span className="spinner" aria-hidden="true" /> : null}
              Nhận thưởng
            </button>
          ) : (
            <span className="hint">Chưa hoàn thành</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function QuestPanel({ onXpChange }: { onXpChange?: () => void }) {
  const toast = useToast();
  const [dangNhanKhoa, setDangNhanKhoa] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    const [streak, questList] = await Promise.all([
      api.getStreak(),
      api.getQuests(),
    ]);
    return { streak, quests: questList.quests };
  }, []);

  const { data, reload } = useAsyncData(fetchAll);

  const nhanThuong = async (questKey: string) => {
    setDangNhanKhoa(questKey);
    try {
      const ketQua = await api.claimQuest(questKey);
      toast.ok(
        ketQua.cosmetic
          ? `Nhận +${ketQua.xp_awarded} XP và vật phẩm ${ketQua.cosmetic.name}!`
          : `Nhận +${ketQua.xp_awarded} XP!`,
      );
      reload();
      onXpChange?.();
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangNhanKhoa(null);
    }
  };

  if (!data) return null;
  const { streak, quests } = data;
  const hangNgay = quests.filter((q) => q.period === "daily");
  const hangTuan = quests.filter((q) => q.period === "weekly");

  return (
    <section className="stack-2" aria-labelledby="acc-nhiem-vu">
      <h2 className="section-title section-title-icon" id="acc-nhiem-vu">
        <IconScroll size={19} /> Chuỗi ngày đọc &amp; nhiệm vụ
      </h2>

      <div className="profile-showcase-card">
        <div className="row-between">
          <div className="stack-2">
            <strong className="streak-title">
              <IconFlame size={18} /> {streak.current_streak} ngày liên tiếp
            </strong>
            <span className="hint">
              Chuỗi dài nhất: {streak.longest_streak} ngày
              {streak.last_read_date
                ? ` · lần đọc gần nhất: ${streak.last_read_date}`
                : ""}
            </span>
          </div>
        </div>
      </div>

      {hangNgay.length > 0 ? (
        <div className="stack-2">
          <span className="label">Nhiệm vụ hằng ngày</span>
          <div className="bento-grid">
            {hangNgay.map((q) => (
              <TheNhiemVu
                key={q.key}
                q={q}
                dangNhan={dangNhanKhoa === q.key}
                onNhan={nhanThuong}
              />
            ))}
          </div>
        </div>
      ) : null}

      {hangTuan.length > 0 ? (
        <div className="stack-2">
          <span className="label">Nhiệm vụ hằng tuần</span>
          <div className="bento-grid">
            {hangTuan.map((q) => (
              <TheNhiemVu
                key={q.key}
                q={q}
                dangNhan={dangNhanKhoa === q.key}
                onNhan={nhanThuong}
              />
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
