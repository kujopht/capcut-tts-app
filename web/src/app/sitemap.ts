import type { MetadataRoute } from "next";
import { API_BASE } from "@/lib/api";

const BASE_URL = "https://fanfic.world";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticEntries: MetadataRoute.Sitemap = [
    {
      url: BASE_URL,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 1.0,
    },
    {
      url: `${BASE_URL}/library`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/fanfic`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/community`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.7,
    },
  ];

  try {
    const res = await fetch(`${API_BASE}/api/novels?limit=50`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return staticEntries;
    const data = await res.json();
    const novels = data.novels ?? [];

    const novelEntries: MetadataRoute.Sitemap = novels.map(
      (novel: { novel_id: string; updated_at?: string }) => ({
        url: `${BASE_URL}/novels/${novel.novel_id}`,
        lastModified: novel.updated_at ? new Date(novel.updated_at) : new Date(),
        changeFrequency: "weekly",
        priority: 0.8,
      }),
    );

    return [...staticEntries, ...novelEntries];
  } catch {
    return staticEntries;
  }
}
