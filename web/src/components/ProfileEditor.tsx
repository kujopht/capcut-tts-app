"use client";

/**
 * Trình sửa hồ sơ — Social & Play V1.
 *
 * MỘT lần lưu cho mọi thứ (`PUT /api/me/profile`): máy chủ kiểm TẤT CẢ trước
 * khi ghi, nên hoặc cả hồ sơ đổi, hoặc không gì đổi — không bao giờ lưu được
 * nửa chừng (avatar mới mà bio cũ vì bio quá dài).
 *
 * XEM TRƯỚC trước khi lưu: đầu hồ sơ (bìa, avatar + khung, tên, màu nhấn,
 * fandom) cập nhật theo từng thay đổi. Huỷ / Esc / bấm ra ngoài khi còn thay
 * đổi chưa lưu thì HỎI LẠI; rời trang cũng vậy (`beforeunload`).
 *
 * Không có "khôi phục ảnh Google": hệ thống chưa bao giờ lưu ảnh Google của ai
 * (xem báo cáo). Nút "Bỏ ảnh tuỳ chỉnh" đưa avatar về chữ cái đầu — nói đúng
 * điều nó làm, không hứa điều không có.
 *
 * Khung avatar lấy từ KHO VẬT PHẨM CÓ SẴN (`/api/account/cosmetics`) — không
 * có cửa hàng hay tiền tệ mới. Máy chủ kiểm quyền sở hữu khi lưu. Khung chỉ là
 * trang trí, không cho lợi thế gì.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ApiError,
  api,
  type CosmeticItem,
  type Profile,
  type ProfileUpdate,
  type ServerLimits,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { useDialogFocus } from "@/lib/useDialogFocus";
import { taiAnh, type AnhCat } from "@/lib/profileImage";
import { ConfirmDialog } from "@/components/ui";
import { ImageCropper } from "@/components/ImageCropper";
import { UserAvatar, khungDangDeo, tenHienThi } from "@/components/UserAvatar";

type ThayAnh = { loai: "giu" } | { loai: "moi"; anh: AnhCat } | { loai: "bo" };

/** Nhãn người đọc được cho từng màu nhấn (khớp `profile_accents` của máy chủ). */
export const NHAN_MAU: Record<string, string> = {
  aurora: "Cực quang",
  ember: "Than hồng",
  jade: "Ngọc bích",
  violet: "Tím huyền",
  gold: "Hoàng kim",
};

const TRAN_BIO_DU_PHONG = 400;

export function ProfileEditor({
  limits,
  onClose,
  onSaved,
}: {
  limits: ServerLimits | null;
  onClose: () => void;
  onSaved: (p: Profile) => void;
}) {
  const { profile, updateProfile } = useSession();
  const cap = limits?.capabilities ?? {};
  const fandoms = limits?.community_fandoms ?? [];
  const accents = limits?.profile_accent_presets ?? [];
  const tranFandom = limits?.profile_max_fandoms ?? 5;
  const gh = limits?.profile_image;
  const tranAvatar = gh?.avatar_max_input_bytes ?? 5 * 1024 * 1024;
  const tranBanner = gh?.banner_max_input_bytes ?? 8 * 1024 * 1024;
  const [avW, avH] = gh?.avatar_output_size ?? [512, 512];
  const [bnW, bnH] = gh?.banner_output_size ?? [1500, 500];

  const [bio, setBio] = useState(profile?.bio ?? "");
  const [chonFandom, setChonFandom] = useState<string[]>(profile?.fandom_ids ?? []);
  const [accent, setAccent] = useState<string | null>(profile?.accent ?? null);
  const [avatar, setAvatar] = useState<ThayAnh>({ loai: "giu" });
  const [banner, setBanner] = useState<ThayAnh>({ loai: "giu" });
  const [khung, setKhung] = useState<string | null | undefined>(undefined);
  const [khungSoHuu, setKhungSoHuu] = useState<CosmeticItem[] | null>(null);
  const [dangCat, setDangCat] = useState<null | { kieu: "avatar" | "banner"; img: HTMLImageElement }>(null);
  const [dangLuu, setDangLuu] = useState(false);
  const [loi, setLoi] = useState("");
  const [hoiBo, setHoiBo] = useState(false);
  const hop = useRef<HTMLDivElement | null>(null);
  const tepAvatar = useRef<HTMLInputElement | null>(null);
  const tepBanner = useRef<HTMLInputElement | null>(null);

  /* Kho khung da so huu — that, tu `/api/account/cosmetics`. */
  useEffect(() => {
    api
      .getCosmetics()
      .then((r) => setKhungSoHuu(r.cosmetics.filter((c) => c.slot === "avatar_frame")))
      .catch(() => setKhungSoHuu([]));
  }, []);

  /* Thu hoi URL blob xem truoc. */
  useEffect(() => {
    const urls = [avatar, banner].flatMap((a) => (a.loai === "moi" ? [a.anh.xemTruoc] : []));
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [avatar, banner]);

  const bioCu = profile?.bio ?? "";
  const fandomCu = useMemo(() => profile?.fandom_ids ?? [], [profile?.fandom_ids]);
  const accentCu = profile?.accent ?? null;
  const doi = useMemo(
    () =>
      bio !== bioCu ||
      chonFandom.join(",") !== fandomCu.join(",") ||
      accent !== accentCu ||
      avatar.loai !== "giu" ||
      banner.loai !== "giu" ||
      khung !== undefined,
    [bio, bioCu, chonFandom, fandomCu, accent, accentCu, avatar, banner, khung],
  );

  /* Roi trang khi con thay doi chua luu: trinh duyet hoi lai. */
  useEffect(() => {
    if (!doi) return;
    const h = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [doi]);

  const thuDong = useCallback(() => {
    // Hop "Bo thay doi?" dang mo: Esc la viec CUA NO, khong phai cua trinh sua.
    if (dangLuu || hoiBo) return;
    if (dangCat) {
      setDangCat(null);
      return;
    }
    if (doi) setHoiBo(true);
    else onClose();
  }, [dangLuu, hoiBo, dangCat, doi, onClose]);

  useDialogFocus(hop, thuDong, true);

  const chonTep = useCallback(async (kieu: "avatar" | "banner", tep: File | undefined) => {
    if (!tep) return;
    setLoi("");
    const tranVao = kieu === "avatar" ? tranAvatar : tranBanner;
    if (!/^image\/(jpeg|png|webp)$/.test(tep.type)) {
      setLoi("Chỉ nhận ảnh JPG, PNG hoặc WebP.");
      return;
    }
    if (tep.size > tranVao) {
      setLoi(`Ảnh quá lớn (${(tep.size / 1024 / 1024).toFixed(1)} MB) — tối đa ${tranVao / 1024 / 1024} MB.`);
      return;
    }
    try {
      setDangCat({ kieu, img: await taiAnh(tep) });
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không đọc được ảnh.");
    }
  }, [tranAvatar, tranBanner]);

  const luu = useCallback(async () => {
    if (!doi || dangLuu) return;
    const goi: ProfileUpdate = {};
    if (bio !== bioCu) goi.bio = bio;
    if (cap.profile_fandoms && chonFandom.join(",") !== fandomCu.join(",")) goi.fandom_ids = chonFandom;
    if (cap.profile_accent && accent !== accentCu) goi.accent = accent;
    if (avatar.loai === "moi") goi.avatar = { data: avatar.anh.base64, mime: avatar.anh.mime };
    if (avatar.loai === "bo") goi.avatar = { remove: true };
    if (cap.profile_banner && banner.loai === "moi") goi.banner = { data: banner.anh.base64, mime: banner.anh.mime };
    if (cap.profile_banner && banner.loai === "bo") goi.banner = { remove: true };
    if (khung !== undefined) goi.frame = khung;
    setDangLuu(true);
    setLoi("");
    try {
      const ra = await api.updateMyProfile(goi);
      updateProfile(ra.profile);
      onSaved(ra.profile);
    } catch (e) {
      // GIU moi thay doi de nguoi dung sua roi luu lai.
      setLoi(
        e instanceof ApiError
          ? `${e.message} Chưa có gì được lưu — các thay đổi của bạn vẫn còn.`
          : "Mất kết nối. Chưa có gì được lưu — các thay đổi của bạn vẫn còn.",
      );
    } finally {
      setDangLuu(false);
    }
  }, [doi, dangLuu, bio, bioCu, cap.profile_fandoms, cap.profile_accent, cap.profile_banner, chonFandom, fandomCu, accent, accentCu, avatar, banner, khung, updateProfile, onSaved]);

  if (!profile) return null;

  const avatarXem =
    avatar.loai === "moi" ? avatar.anh.xemTruoc : avatar.loai === "bo" ? null : profile.avatar_url ?? null;
  const bannerXem =
    banner.loai === "moi" ? banner.anh.xemTruoc : banner.loai === "bo" ? null : profile.banner_url ?? null;
  const khungXem: CosmeticItem | null =
    khung === undefined ? khungDangDeo(profile) : khung === null ? null : khungSoHuu?.find((c) => c.key === khung) ?? null;
  const tranBio = TRAN_BIO_DU_PHONG;

  // Portal: `.page` co `transform`, `fixed` ben trong no khong phu man hinh.
  return createPortal(
    <div
      className="lop-phu soan-lop-phu"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) thuDong();
      }}
    >
      <div ref={hop} className="hop-thoai soan-hop sua-ho-so" role="dialog" aria-modal="true" aria-labelledby="sua-ho-so-tieu-de" tabIndex={-1}>
        <header className="soan-hop-dau">
          <h2 id="sua-ho-so-tieu-de" className="h3">
            Sửa hồ sơ
          </h2>
          <button type="button" className="btn btn-ghost btn-sm soan-hop-dong" aria-label="Đóng" onClick={thuDong} disabled={dangLuu}>
            ✕
          </button>
        </header>

        <div className="soan-hop-than">
          {/* XEM TRUOC — dung nhu nguoi khac se thay. */}
          <section className="ho-so-xem-truoc" data-accent={accent ?? undefined} aria-label="Xem trước hồ sơ">
            <div className="ho-so-bia ho-so-bia-nho" style={bannerXem ? { backgroundImage: `url("${bannerXem}")` } : undefined} />
            <div className="ho-so-xem-truoc-dau">
              <UserAvatar user={{ ...profile, avatar_url: avatarXem }} frame={khungXem} className="account-avatar" />
              <div className="ho-so-xem-truoc-chu">
                <strong>{tenHienThi(profile)}</strong>
                {profile.username ? <span className="hint">@{profile.username}</span> : null}
                {bio.trim() ? <span className="hint ho-so-xem-truoc-bio">{bio.trim()}</span> : null}
                {chonFandom.length ? (
                  <span className="ho-so-fandom-hang">
                    {chonFandom.map((id) => (
                      <span key={id} className="chip chip-static">
                        {fandoms.find((f) => f.id === id)?.label ?? id}
                      </span>
                    ))}
                  </span>
                ) : null}
              </div>
            </div>
          </section>

          {dangCat ? (
            <ImageCropper
              img={dangCat.img}
              kieu={dangCat.kieu}
              outW={dangCat.kieu === "avatar" ? avW : bnW}
              outH={dangCat.kieu === "avatar" ? avH : bnH}
              onCancel={() => setDangCat(null)}
              onDone={(anh) => {
                if (dangCat.kieu === "avatar") setAvatar({ loai: "moi", anh });
                else setBanner({ loai: "moi", anh });
                setDangCat(null);
              }}
            />
          ) : (
            <>
              <fieldset className="sua-ho-so-nhom">
                <legend>Ảnh đại diện</legend>
                <div className="row sua-ho-so-nut">
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => tepAvatar.current?.click()}>
                    Tải ảnh lên…
                  </button>
                  {avatarXem || avatar.loai === "moi" ? (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAvatar({ loai: "bo" })}>
                      Bỏ ảnh tuỳ chỉnh
                    </button>
                  ) : null}
                  {avatar.loai !== "giu" ? (
                    <button type="button" className="link-btn" onClick={() => setAvatar({ loai: "giu" })}>
                      Hoàn tác
                    </button>
                  ) : null}
                </div>
                <p className="hint">
                  JPG, PNG hoặc WebP, tối đa {Math.round(tranAvatar / 1024 / 1024)} MB. Máy chủ lưu bản {avW}×{avH} đã bỏ metadata.
                </p>
                <input
                  ref={tepAvatar}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  hidden
                  onChange={(e) => {
                    void chonTep("avatar", e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
              </fieldset>

              {cap.profile_banner ? (
                <fieldset className="sua-ho-so-nhom">
                  <legend>Ảnh bìa</legend>
                  <div className="row sua-ho-so-nut">
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => tepBanner.current?.click()}>
                      Tải ảnh bìa…
                    </button>
                    {bannerXem ? (
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setBanner({ loai: "bo" })}>
                        Bỏ ảnh bìa
                      </button>
                    ) : null}
                    {banner.loai !== "giu" ? (
                      <button type="button" className="link-btn" onClick={() => setBanner({ loai: "giu" })}>
                        Hoàn tác
                      </button>
                    ) : null}
                  </div>
                  <p className="hint">
                    Tỉ lệ 3:1, tối đa {Math.round(tranBanner / 1024 / 1024)} MB. Máy chủ lưu bản {bnW}×{bnH}.
                  </p>
                  <input
                    ref={tepBanner}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    hidden
                    onChange={(e) => {
                      void chonTep("banner", e.target.files?.[0]);
                      e.target.value = "";
                    }}
                  />
                </fieldset>
              ) : null}

              <label className="sua-ho-so-nhom">
                <span className="sua-ho-so-nhan">Giới thiệu ngắn</span>
                <textarea className="input" rows={3} maxLength={tranBio} value={bio} onChange={(e) => setBio(e.target.value)} />
                <span className="hint">{tranBio - bio.length} ký tự</span>
              </label>

              {cap.profile_fandoms && fandoms.length ? (
                <fieldset className="sua-ho-so-nhom">
                  <legend>Fandom yêu thích (tối đa {tranFandom})</legend>
                  <div className="ho-so-fandom-hang">
                    {fandoms.map((f) => {
                      const co = chonFandom.includes(f.id);
                      return (
                        <button
                          key={f.id}
                          type="button"
                          className="chip"
                          aria-pressed={co}
                          disabled={!co && chonFandom.length >= tranFandom}
                          onClick={() => setChonFandom((ds) => (co ? ds.filter((x) => x !== f.id) : [...ds, f.id]))}
                        >
                          {f.label}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
              ) : null}

              {cap.profile_accent && accents.length ? (
                <fieldset className="sua-ho-so-nhom">
                  <legend>Màu nhấn</legend>
                  <div className="ho-so-mau-hang">
                    <label className="ho-so-mau" data-accent="">
                      <input type="radio" name="accent" checked={accent === null} onChange={() => setAccent(null)} />
                      <span className="ho-so-mau-o" aria-hidden="true" />
                      <span>Mặc định</span>
                    </label>
                    {accents.map((a) => (
                      <label key={a} className="ho-so-mau" data-accent={a}>
                        <input type="radio" name="accent" checked={accent === a} onChange={() => setAccent(a)} />
                        <span className="ho-so-mau-o" aria-hidden="true" />
                        <span>{NHAN_MAU[a] ?? a}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              ) : null}

              <fieldset className="sua-ho-so-nhom">
                <legend>Khung ảnh đại diện</legend>
                {khungSoHuu === null ? (
                  <p className="hint">Đang tải kho vật phẩm…</p>
                ) : (
                  <div className="ho-so-khung-hang">
                    <label className="ho-so-khung">
                      <input
                        type="radio"
                        name="frame"
                        checked={khungXem === null}
                        onChange={() => setKhung(null)}
                      />
                      <UserAvatar user={{ ...profile, avatar_url: avatarXem }} frame={null} className="avatar" />
                      <span>Không khung</span>
                    </label>
                    {khungSoHuu.map((c) => (
                      <label key={c.key} className="ho-so-khung">
                        <input
                          type="radio"
                          name="frame"
                          checked={khungXem?.key === c.key}
                          onChange={() => setKhung(c.key)}
                        />
                        <UserAvatar user={{ ...profile, avatar_url: avatarXem }} frame={c} className="avatar" />
                        <span>{c.name}</span>
                      </label>
                    ))}
                    {khungSoHuu.length === 0 ? (
                      <p className="hint">Bạn chưa có khung nào — khung mở khoá qua thành tựu và gói lên bậc.</p>
                    ) : null}
                  </div>
                )}
              </fieldset>
            </>
          )}

          {loi ? (
            <p className="hint loi" role="alert">
              {loi}
            </p>
          ) : null}
        </div>

        <footer className="soan-hop-day">
          <span className="hint" aria-live="polite">
            {dangLuu ? "Đang lưu…" : doi ? "Có thay đổi chưa lưu" : "Chưa có thay đổi"}
          </span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={thuDong} disabled={dangLuu}>
            Huỷ
          </button>
          <button type="button" className="btn btn-primary btn-sm" disabled={!doi || dangLuu || !!dangCat} aria-busy={dangLuu} onClick={() => void luu()}>
            {dangLuu ? "Đang lưu…" : "Lưu hồ sơ"}
          </button>
        </footer>
      </div>

      <ConfirmDialog
        open={hoiBo}
        title="Bỏ các thay đổi chưa lưu?"
        body="Những gì bạn vừa sửa sẽ mất."
        confirmLabel="Bỏ thay đổi"
        cancelLabel="Sửa tiếp"
        danger
        onConfirm={() => {
          setHoiBo(false);
          onClose();
        }}
        onCancel={() => setHoiBo(false)}
      />
    </div>,
    document.body,
  );
}
