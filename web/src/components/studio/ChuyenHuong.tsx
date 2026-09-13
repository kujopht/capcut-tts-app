"use client";

/**
 * CHUYEN HUONG mot duong dan Studio cu sang diem den moi.
 *
 * Vi sao khong dung `redirect()` cua server component: dich den mang QUERY
 * (`?mode=audio`, `?tab=translate`), va ta muon giu nguyen moi tham so khac
 * nguoi dung mang theo — mot lien ket `/studio/video?project=vpr_x` phai
 * thanh `/studio/media?project=vpr_x`, khong phai vut mat `project`.
 *
 * Va vi sao KHONG dung chuyen huong 308 o `next.config`: mot 308 duoc trinh
 * duyet nho VINH VIEN. Dat nham mot dich den la dat nham cho moi nguoi da
 * ghe qua, ke ca sau khi ta sua lai — §17 goi dung ten no, "avoid unnecessary
 * permanent redirect chains".
 *
 * `replace` chu khong phai `push`: nguoi dung khong bao gio nen bam Back roi
 * roi lai vao dung cai duong dan vua dua ho di.
 */

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loading } from "@/components/ui";

export function ChuyenHuong({ den }: { den: string }) {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const [duong, queryDich] = den.split("?");
    const q = new URLSearchParams(queryDich || "");
    // Tham so nguoi dung mang theo THANG hon mac dinh cua dich: mot lien ket
    // da ghi ro `?tab=` thi phai duoc ton trong.
    params.forEach((v, k) => q.set(k, v));
    const chuoi = q.toString();
    router.replace(chuoi ? `${duong}?${chuoi}` : duong);
  }, [den, params, router]);

  return <Loading />;
}
