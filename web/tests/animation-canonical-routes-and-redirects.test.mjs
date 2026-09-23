import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import nextConfig from "../next.config.mjs";

test("next.config.mjs redirects: preserves canonical animation routes and excludes wildcards", async () => {
  const redirects = await nextConfig.redirects();
  
  // 1. Verify /animation is NOT redirected
  const animRoot = redirects.find(r => r.source === "/animation");
  assert.equal(animRoot, undefined, "/animation must remain canonical (NOT in redirects)");

  // 2. Verify no wildcard redirect captures /animation/:path*
  const animWildcard = redirects.find(r => r.source === "/animation/:path*");
  assert.equal(animWildcard, undefined, "/animation/:path* must NOT exist in redirects");

  // 3. Verify /animation/new redirect to /admin/animation/sources/new with permanent: true (308)
  const animNew = redirects.find(r => r.source === "/animation/new");
  assert.ok(animNew, "thiếu chuyển hướng /animation/new");
  assert.equal(animNew.destination, "/admin/animation/sources/new");
  assert.equal(animNew.permanent, true);

  // 4. Verify /fanfic -> /library?tab=fanfic preserved
  const fanfic = redirects.find(r => r.source === "/fanfic");
  assert.ok(fanfic, "thiếu chuyển hướng /fanfic");
  assert.equal(fanfic.destination, "/library?tab=fanfic");
  assert.equal(fanfic.permanent, true);

  // 5. Verify /import -> /studio/write/import preserved
  const imp = redirects.find(r => r.source === "/import");
  assert.ok(imp, "thiếu chuyển hướng /import");
  assert.equal(imp.destination, "/studio/write/import");
  assert.equal(imp.permanent, true);
});

test("canonical animation and entertainment page files exist on disk", () => {
  const files = [
    "src/app/animation/page.tsx",
    "src/app/animation/[id]/page.tsx",
    "src/app/animation/watch/[id]/page.tsx",
    "src/app/entertainment/page.tsx",
    "src/app/admin/animation/sources/new/page.tsx",
  ];

  for (const f of files) {
    const fullPath = new URL(`../${f}`, import.meta.url);
    assert.ok(existsSync(fullPath), `Tệp trang bắt buộc ${f} phải tồn tại`);
    const content = readFileSync(fullPath, "utf8");
    assert.ok(content.length > 50, `Tệp ${f} phải có nội dung hợp lệ`);
  }
});

test("redirect matching simulation: canonical routes remain 200, /animation/new yields 308, no loops", async () => {
  const redirects = await nextConfig.redirects();

  function matchRedirect(path) {
    for (const rule of redirects) {
      if (rule.source === path) {
        return { matched: true, destination: rule.destination, permanent: rule.permanent, status: rule.permanent ? 308 : 307 };
      }
      if (rule.source.endsWith("/:path*")) {
        const prefix = rule.source.replace("/:path*", "");
        if (path.startsWith(prefix + "/") || path === prefix) {
          return { matched: true, destination: rule.destination, permanent: rule.permanent, status: rule.permanent ? 308 : 307 };
        }
      }
    }
    return { matched: false, status: 200 };
  }

  // 1. /animation -> 200 (not redirected)
  const rRoot = matchRedirect("/animation");
  assert.equal(rRoot.matched, false);
  assert.equal(rRoot.status, 200);

  // 2. /animation/<real-series-id> -> 200 (not redirected)
  const rSeries = matchRedirect("/animation/series_dragon_ball_super_01");
  assert.equal(rSeries.matched, false);
  assert.equal(rSeries.status, 200);

  // 3. /animation/watch/<real-episode-id> -> 200 (not redirected)
  const rEpisode = matchRedirect("/animation/watch/ep_dbs_131_final");
  assert.equal(rEpisode.matched, false);
  assert.equal(rEpisode.status, 200);

  // 4. /animation/new -> 308 to /admin/animation/sources/new
  const rNew = matchRedirect("/animation/new");
  assert.equal(rNew.matched, true);
  assert.equal(rNew.status, 308);
  assert.equal(rNew.destination, "/admin/animation/sources/new");

  // 5. /entertainment -> 200 (not redirected)
  const rEntertain = matchRedirect("/entertainment");
  assert.equal(rEntertain.matched, false);
  assert.equal(rEntertain.status, 200);

  // 6. Verify no redirect loop on the destination of /animation/new
  const rDest = matchRedirect(rNew.destination);
  assert.equal(rDest.matched, false, "Destination /admin/animation/sources/new must NOT redirect further");
  assert.equal(rDest.status, 200);

  // 7. Verify no redirect loop on /library?tab=fanfic
  const rFanficDest = matchRedirect("/library");
  assert.equal(rFanficDest.matched, false, "/library must NOT redirect");
  assert.equal(rFanficDest.status, 200);

  // 8. Verify no redirect loop on /studio/write/import
  const rImportDest = matchRedirect("/studio/write/import");
  assert.equal(rImportDest.matched, false, "/studio/write/import must NOT redirect");
  assert.equal(rImportDest.status, 200);
});
