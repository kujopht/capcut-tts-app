"use client";

/**
 * Tao series Animation moi (overnight Phase 5, V6).
 *
 * Sau khi tao, dieu huong sang trang quan ly cua CHINH series do
 * (`/animation/{id}`) — chu so huu thay ngay khu them tap va nut xuat ban.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { PageHeader } from "@/components/ui";
import { IconFilm } from "@/components/Icons";

export default function NewAnimationSeriesPage() {
  const router = useRouter();
  const { profile, loading } = useSession();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dangTao, setDangTao] = useState(false);
  const [loi, setLoi] = useState("");

  if (loading) return null;
  if (!profile) {
    router.replace("/login");
    return null;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setLoi("Cần có tên series.");
      return;
    }
    setDangTao(true);
    setLoi("");
    try {
      const { series } = await api.createAnimationSeries(
        title, description, [],
      );
      router.push(`/animation/${series.series_id}`);
    } catch (cause) {
      setLoi(errorMessage(cause));
      setDangTao(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Animation"
        icon={<IconFilm />}
        title="Tạo series mới"
        lead="Series là tập hợp các tập video YouTube. Bạn thêm tập sau khi tạo xong."
      />
      <form className="card stack-3" onSubmit={submit}>
        <div className="field">
          <label className="label" htmlFor="anim-title">
            Tên series
          </label>
          <input
            id="anim-title"
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ví dụ: Hải Tặc Vùng Đông (bản chuyển thể)"
            maxLength={200}
            required
          />
        </div>
        <div className="field">
          <label className="label" htmlFor="anim-desc">
            Mô tả
          </label>
          <textarea
            id="anim-desc"
            className="input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
          />
        </div>
        {loi ? (
          <p className="hint" role="alert">
            {loi}
          </p>
        ) : null}
        <button type="submit" className="btn btn-primary" disabled={dangTao}>
          {dangTao ? "Đang tạo…" : "Tạo series"}
        </button>
      </form>
    </div>
  );
}
