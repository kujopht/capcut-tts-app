"use client";

/**
 * Diem tra ve sau khi Google/Facebook xac thuc xong.
 *
 * Appwrite dieu huong trinh duyet toi day kem `userId` va `secret` — mot cap
 * DUNG MOT LAN. Trang nay chi lam mot viec: doi no lay token cua ung dung,
 * roi di tiep.
 *
 * BON QUY TAC VE CAP DO, moi cai chong mot duong ro ri that:
 *
 *  1. Doc NGAY vao bien cuc bo roi XOA khoi thanh dia chi bang
 *     `history.replaceState`. Neu khong, secret nam lai trong lich su trinh
 *     duyet, trong `document.referrer` cua moi request tiep theo, va trong
 *     log cua bat ky proxy nao.
 *  2. KHONG ghi vao `localStorage`/`sessionStorage`. Thu duy nhat duoc luu la
 *     token cua ung dung — cung thu ma dang nhap bang mat khau luu.
 *  3. Doi NGAY, khong cho thao tac nguoi dung. Cap nay het han nhanh, va giu
 *     no lau hon can thiet khong duoc gi.
 *  4. Loi thi ve `/login` voi mot cau tieng Viet. KHONG hien ngoai le goc cua
 *     Appwrite, `userId`, `secret` hay token — chung khong noi gi huu ich cho
 *     nguoi dung va co the chua manh credential.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { safeNext } from "@/lib/nav";
import { Alert, Loading } from "@/components/ui";

const TEN_NHA_CUNG_CAP: Record<string, string> = {
  google: "Google",
  facebook: "Facebook",
};

export default function OAuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="page">
          <Loading label="Đang đăng nhập…" />
        </div>
      }
    >
      <OAuthCallback />
    </Suspense>
  );
}

function OAuthCallback() {
  const router = useRouter();
  const params = useSearchParams();
  const { adoptSession } = useSession();
  const [error, setError] = useState("");

  /*
    Doc MOT LAN, ngay o lan render dau.

    Hieu ung `history.replaceState` ben duoi xoa toan bo query — ke ca
    `provider`. `useSearchParams` doc lai va tra ve rong, nen neu tinh nhan tu
    no thi man hinh chuyen tu "Đang đăng nhập với Google…" thanh "…với nhà
    cung cấp…" ngay truoc mat nguoi dung. Da thay bang trinh duyet that.

    Ham khoi tao cua `useState` chay dung mot lan, nen gia tri nay khong doi
    theo URL nua.
  */
  const [ten] = useState(
    () => TEN_NHA_CUNG_CAP[params.get("provider") ?? ""] ?? "nhà cung cấp",
  );

  /*
    React 18 goi effect HAI LAN o che do nghiem ngat khi phat trien. Cap
    dung-mot-lan thi lan doi thu hai CHAC CHAN hong, va nguoi dung se thay mot
    thong bao loi sau khi da dang nhap thanh cong. Cai cong nay chan dung cho
    do — no khong phai toi uu.
  */
  const daChay = useRef(false);

  useEffect(() => {
    if (daChay.current) return;
    daChay.current = true;

    const userId = params.get("userId") ?? "";
    const secret = params.get("secret") ?? "";
    const next = safeNext(params.get("next"));

    /*
      MOI nhanh nam trong chuoi bat dong bo, khong co `setState` nao trong
      than effect — quy tac `react-hooks/set-state-in-effect`, cung ly do
      `lib/useAsyncData.ts` ton tai.

      Ham nay KHONG nem: no tra ve ket cuc, vi "thieu tham so" va "doi that
      bai" can hai cau khac nhau, con `catch` thi khong phan biet duoc.
    */
    const doi = async (): Promise<
      | { kind: "ok"; token: string; profile: Awaited<ReturnType<typeof api.exchangeOAuth>>["profile"] }
      | { kind: "thieu" }
      | { kind: "hong" }
    > => {
      // Xoa cap khoi thanh dia chi TRUOC khi goi mang. Lam sau thi da co mot
      // request di ra kem `Referer` chua secret.
      window.history.replaceState(null, "", "/auth/callback");
      if (!userId || !secret) return { kind: "thieu" };
      try {
        const result = await api.exchangeOAuth(userId, secret);
        return { kind: "ok", token: result.token, profile: result.profile };
      } catch {
        // Co y KHONG dung `errorMessage(cause)`: thong diep tu may chu o duong
        // nay da duoc lam sach, nhung mot loi mang tho van co the mang theo
        // URL day du — ma URL do vua chua secret.
        return { kind: "hong" };
      }
    };

    doi().then((ket_qua) => {
      if (ket_qua.kind === "ok") {
        adoptSession(ket_qua.token, ket_qua.profile);
        router.replace(next);
        return;
      }
      setError(
        ket_qua.kind === "thieu"
          ? `Thiếu thông tin đăng nhập từ ${ten}. Vui lòng thử đăng nhập lại.`
          : `Đăng nhập bằng ${ten} không thành công. Liên kết có thể đã hết hạn hoặc đã được dùng.`,
      );
    });
  }, [params, router, adoptSession, ten]);

  if (error) {
    return (
      <div className="page auth-callback">
        <Alert kind="error">{error}</Alert>
        <Link className="btn btn-primary" href="/login" prefetch={false}>
          Về trang đăng nhập
        </Link>
      </div>
    );
  }

  return (
    <div className="page auth-callback">
      <Loading label={`Đang đăng nhập với ${ten}…`} />
    </div>
  );
}
