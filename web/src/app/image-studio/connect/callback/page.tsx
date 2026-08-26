"use client";

/**
 * Diem tra ve sau khi Pollinations xac thuc xong (BYOP OAuth PKCE).
 *
 * Cung 4 quy tac voi `app/auth/callback/page.tsx` (xem docstring o do):
 *  1. Doc NGAY roi xoa khoi thanh dia chi bang `history.replaceState`.
 *  2. KHONG ghi `code`/`state` vao localStorage/sessionStorage.
 *  3. Doi NGAY, khong cho thao tac nguoi dung.
 *  4. Loi thi hien mot cau tieng Viet chung — KHONG hien ngoai le goc/`code`.
 *
 * `redirect_uri` gui len PHAI khop CHINH XAC voi `IMAGE_BYOP_REDIRECT_URI`
 * ma backend dung khi dung `bat_dau_ket_noi` — day chinh la URL trang nay,
 * nen dung `window.location.origin + pathname` (khong query) thay vi hard-
 * code, de tu dong dung o moi moi truong (dev/staging/production).
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { imageStudio } from "@/lib/api";
import { Alert, Loading } from "@/components/ui";

export default function ImageStudioByopCallbackPage() {
  return (
    <Suspense fallback={<Loading label="Đang xử lý…" />}>
      <ByopCallbackInner />
    </Suspense>
  );
}

function ByopCallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState("");
  const daChay = useRef(false);

  useEffect(() => {
    if (daChay.current) return;
    daChay.current = true;

    /*
      MOI nhanh nam trong chuoi bat dong bo, khong co `setState` nao trong
      than effect — cung khuon voi `app/auth/callback/page.tsx` (quy tac
      `react-hooks/set-state-in-effect`).
    */
    const doi = async (): Promise<{ kind: "ok" } | { kind: "thieu" } | { kind: "hong" }> => {
      const state = params.get("state") ?? "";
      const code = params.get("code") ?? "";
      const oauthError = params.get("error") ?? "";

      // Xoa ngay khoi thanh dia chi — khong de code/state nam trong lich su
      // trinh duyet hay document.referrer cua request tiep theo.
      window.history.replaceState(null, "", "/image-studio/connect/callback");

      if (oauthError || !state || !code) return { kind: "thieu" };

      const redirectUri = `${window.location.origin}/image-studio/connect/callback`;
      try {
        await imageStudio.imageByopCallback(state, code, redirectUri);
        return { kind: "ok" };
      } catch {
        return { kind: "hong" };
      }
    };

    doi().then((ket_qua) => {
      if (ket_qua.kind === "ok") {
        router.replace("/image-studio");
        return;
      }
      setError(
        ket_qua.kind === "thieu"
          ? "Kết nối Pollinations không thành công hoặc đã bị huỷ."
          : "Không hoàn tất được kết nối Pollinations — vui lòng thử lại.",
      );
    });
  }, [params, router]);

  if (error) {
    return (
      <div className="page">
        <Alert kind="error">{error}</Alert>
        <p className="hint">
          <Link href="/image-studio" prefetch={false}>Quay lại Image Studio</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <Loading label="Đang hoàn tất kết nối Pollinations…" />
    </div>
  );
}
