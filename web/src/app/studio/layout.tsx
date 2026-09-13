import { StudioShell } from "@/components/StudioShell";

/**
 * Khung cho MOI trang duoi `/studio`.
 *
 * Dat thanh ben o layout chu khong o tung trang, cung ly do voi
 * `app/admin/layout.tsx`: mot cong cu moi them vao `/studio/*` phai TU CO
 * dieu huong. Mot trang quen goi khung la mot trang nguoi dung vao roi khong
 * co duong ra — va do la loai loi khong ai bao cao, ho chi roi di.
 */
export default function StudioLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <StudioShell>{children}</StudioShell>;
}
