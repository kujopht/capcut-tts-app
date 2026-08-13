import { AdminShell } from "@/components/AdminShell";

/**
 * Khung cho MOI trang duoi `/admin`.
 *
 * Dat cong chan o layout chu khong o tung trang: mot trang moi duoc them ma
 * quen goi cong se la mot trang khong duoc bao ve, va do la loai loi khong ai
 * phat hien cho toi khi da muon.
 *
 * Cong nay chi lo GIAO DIEN. Du lieu duoc bao ve o may chu — moi route
 * `/api/admin/*` deu di qua `Depends(admin_profile)`, nen mot nguoi dung thuong
 * go thang duong dan se thay khung nay tu choi VA khong mot lenh goi du lieu nao
 * cua ho tra ve gi.
 */
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AdminShell>{children}</AdminShell>;
}
