import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: [
          "/",
          "/library",
          "/fanfic",
          "/novels/",
          "/chapters/",
          "/community",
        ],
        disallow: [
          "/admin/",
          "/studio/",
          "/account/",
          "/write/",
          "/api/",
        ],
      },
    ],
    sitemap: "https://fanfic.world/sitemap.xml",
  };
}
