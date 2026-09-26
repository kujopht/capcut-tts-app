"use client";

/**
 * "Đã chặn / Đã ẩn" trong trang Tài khoản (Social & Play V1).
 *
 * Chặn một người làm bài của họ biến khỏi bảng tin — nên không có chỗ này thì
 * người dùng KHÔNG CÒN đường nào tìm lại họ để bỏ chặn. Dữ liệu thật từ
 * `/api/me/blocks`; chỉ vẽ khi máy chủ bật `capabilities.blocks`.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, social, type AuthorCard, type BlockList } from "@/lib/api";
import { hoSoHref } from "@/lib/communityFeed";
import { UserAvatar, tenHienThi } from "@/components/UserAvatar";

function Hang({
  nguoi,
  nhanNut,
  onBo,
}: {
  nguoi: AuthorCard;
  nhanNut: string;
  onBo: () => Promise<void>;
}) {
  const [dang, setDang] = useState(false);
  const href = hoSoHref(nguoi);
  return (
    <li className="sidebar-nguoi">
      <UserAvatar user={nguoi} className="avatar avatar-sm" />
      <span className="sidebar-nguoi-chu">
        {href ? (
          <Link href={href} className="sidebar-ten" prefetch={false}>
            {tenHienThi(nguoi)}
          </Link>
        ) : (
          <span className="sidebar-ten">{tenHienThi(nguoi)}</span>
        )}
      </span>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        disabled={dang}
        onClick={async () => {
          setDang(true);
          try {
            await onBo();
          } finally {
            setDang(false);
          }
        }}
      >
        {dang ? "Đang bỏ…" : nhanNut}
      </button>
    </li>
  );
}

export function BlockedUsersPanel() {
  const [ds, setDs] = useState<BlockList | null>(null);
  const [batTinhNang, setBatTinhNang] = useState<boolean | null>(null);
  const [loi, setLoi] = useState("");

  const tai = useCallback(() => {
    social
      .myBlocks()
      .then(setDs)
      .catch((e) => setLoi(e instanceof ApiError ? e.message : "Không tải được danh sách."));
  }, []);

  useEffect(() => {
    social
      .limits()
      .then((l) => {
        const co = Boolean(l.capabilities?.blocks);
        setBatTinhNang(co);
        if (co) tai();
      })
      .catch(() => setBatTinhNang(false));
  }, [tai]);

  if (!batTinhNang) return null;

  const bo = async (kieu: "block" | "mute", userId: string) => {
    setLoi("");
    try {
      if (kieu === "block") await social.unblock(userId);
      else await social.unmute(userId);
      tai();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    }
  };

  return (
    <section className="surface-secondary stack card-tight" aria-labelledby="acc-chan">
      <h2 className="section-title" id="acc-chan">
        Đã chặn và đã ẩn
      </h2>
      <p className="hint">
        Người bị chặn không thấy bài của bạn và không tương tác được với bạn; người bị ẩn chỉ biến khỏi bảng tin
        của bạn. Họ không nhận thông báo nào về việc này.
      </p>
      {loi ? (
        <p className="hint loi" role="alert">
          {loi}
        </p>
      ) : null}
      {ds === null ? (
        <p className="hint">Đang tải…</p>
      ) : ds.blocked.length === 0 && ds.muted.length === 0 ? (
        <p className="hint">Bạn chưa chặn hay ẩn ai.</p>
      ) : (
        <>
          {ds.blocked.length ? (
            <>
              <p className="sidebar-tieu-de">Đã chặn</p>
              <ul className="sidebar-ds">
                {ds.blocked.map((n) => (
                  <Hang key={n.user_id} nguoi={n} nhanNut="Bỏ chặn" onBo={() => bo("block", n.user_id)} />
                ))}
              </ul>
            </>
          ) : null}
          {ds.muted.length ? (
            <>
              <p className="sidebar-tieu-de">Đã ẩn bài</p>
              <ul className="sidebar-ds">
                {ds.muted.map((n) => (
                  <Hang key={n.user_id} nguoi={n} nhanNut="Bỏ ẩn" onBo={() => bo("mute", n.user_id)} />
                ))}
              </ul>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}
