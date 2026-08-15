"use client";

/**
 * Cap do, danh xung, bo suu tap CUA CHINH MINH — V4 visual completion, vong 2
 * (Phan G-L: XP/Level/Title/Cosmetic/Gacha THAT, khong con chi la thiet ke).
 *
 * TACH RIENG khoi `AchievementGrid` (da co tu vong 1) — hai module doc lap,
 * ghep chung trong `/account` qua thu tu JSX chu khong phai mot component.
 */

import { useCallback, useState } from "react";
import { api, type CosmeticItem } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { errorMessage } from "@/lib/session";
import { ProgressBar } from "@/components/ui";
import { IconLibrary } from "@/components/Icons";
import { BadgeIcon, CosmeticFrame, OrnamentIcon } from "@/components/cosmetics/Cosmetics";

function TheVatPham({
  cosmetic,
  onTrangBi,
}: {
  cosmetic: CosmeticItem;
  onTrangBi: (key: string) => void;
}) {
  return (
    <button
      type="button"
      className={`achievement-card do-hiem-${cosmetic.rarity}${
        cosmetic.equipped ? "" : " achievement-card-locked"
      }`}
      onClick={() => onTrangBi(cosmetic.key)}
      disabled={cosmetic.equipped}
      aria-pressed={cosmetic.equipped}
    >
      <span className="achievement-card-icon" aria-hidden="true">
        {cosmetic.slot === "avatar_frame" ? (
          <CosmeticFrame cosmetic={cosmetic}>
            <span className="cosmetic-frame-preview" />
          </CosmeticFrame>
        ) : cosmetic.slot === "badge" ? (
          <BadgeIcon assetRef={cosmetic.asset_ref} />
        ) : (
          <OrnamentIcon assetRef={cosmetic.asset_ref} />
        )}
      </span>
      <span className="progress-card-body">
        <strong>{cosmetic.name}</strong>
        <span className="hint">
          {cosmetic.equipped ? "Đang trang bị" : "Bấm để trang bị"}
        </span>
      </span>
    </button>
  );
}

export function GamificationPanel({
  refreshKey,
}: {
  /** Tang gia tri nay (vi du sau khi nhan thuong nhiem vu o `QuestPanel`) de
      buoc tai lai — XP co the doi o mot component khac ma panel nay khong
      tu biet. */
  refreshKey?: number;
} = {}) {
  const toast = useToast();
  const [dangMoGoi, setDangMoGoi] = useState(false);

  const fetchAll = useCallback(async () => {
    const [progress, titleList, cosmeticList] = await Promise.all([
      api.getProgress(),
      api.getTitles(),
      api.getCosmetics(),
    ]);
    return { progress, titles: titleList.titles, cosmetics: cosmeticList.cosmetics };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const { data, reload } = useAsyncData(fetchAll);

  const chonDanhXung = async (titleKey: string) => {
    try {
      await api.equipTitle(titleKey);
      reload();
    } catch (cause) {
      toast.error(errorMessage(cause));
    }
  };

  const trangBiVatPham = async (cosmeticKey: string) => {
    try {
      await api.equipCosmetic(cosmeticKey);
      reload();
    } catch (cause) {
      toast.error(errorMessage(cause));
    }
  };

  const moGoiThuong = async () => {
    setDangMoGoi(true);
    try {
      const ketQua = await api.openRewardPack("goi_len_bac");
      toast.ok(
        ketQua.duplicate
          ? `Nhận được ${ketQua.cosmetic.name} (đã có sẵn).`
          : `Nhận được vật phẩm mới: ${ketQua.cosmetic.name}!`,
      );
      reload();
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangMoGoi(false);
    }
  };

  if (!data) return null;
  const { progress, titles, cosmetics } = data;

  return (
    <section className="stack-2" aria-labelledby="acc-cap-do">
      <h2 className="section-title section-title-icon" id="acc-cap-do">
        <IconLibrary size={19} /> Cấp độ &amp; bộ sưu tập
      </h2>

      <div className="profile-showcase-card">
        <div className="row-between">
          <div className="stack-2">
            <strong>
              Bậc {progress.level} · {progress.equipped_title}
            </strong>
            <span className="hint">
              {progress.xp} XP
              {progress.next_level_xp
                ? ` · còn ${progress.next_level_xp - progress.xp} XP để lên bậc tiếp theo`
                : " · đã ở bậc cao nhất"}
            </span>
          </div>
          {progress.pending_reward_packs > 0 ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={moGoiThuong}
              disabled={dangMoGoi}
            >
              {dangMoGoi ? <span className="spinner" aria-hidden="true" /> : null}
              Mở gói thưởng ({progress.pending_reward_packs})
            </button>
          ) : null}
        </div>
        <ProgressBar percent={progress.progress_percent} label="Tiến trình lên bậc" />
      </div>

      <div className="stack-2">
        <span className="label">Danh xưng</span>
        <div className="chip-rail" role="group" aria-label="Chọn danh xưng">
          {titles.map((t) => (
            <button
              key={t.key}
              type="button"
              className="chip"
              disabled={!t.unlocked}
              aria-pressed={progress.equipped_title_key === t.key}
              onClick={() => chonDanhXung(t.key)}
              title={t.unlocked ? undefined : `Mở khoá ở bậc ${t.level} (${t.min_xp} XP)`}
            >
              {t.title}
              {!t.unlocked ? " 🔒" : ""}
            </button>
          ))}
        </div>
      </div>

      {cosmetics.length > 0 ? (
        <div className="stack-2">
          <span className="label">Vật phẩm sưu tầm</span>
          <div className="bento-grid">
            {cosmetics.map((c) => (
              <TheVatPham key={c.key} cosmetic={c} onTrangBi={trangBiVatPham} />
            ))}
          </div>
        </div>
      ) : (
        <p className="hint">
          Chưa có vật phẩm nào — lên bậc để nhận gói thưởng miễn phí đầu tiên.
        </p>
      )}
    </section>
  );
}
