/**
 * Bao ve cau hinh chong Cloudflare Error 1102 ("Worker exceeded resource
 * limits").
 *
 * BOI CANH. Mot nguoi dung that gap 1102 o lan dau vao
 * `/admin/authors/applications`. Nguyen nhan: `open-next.config.ts` truoc day
 * goi `defineCloudflareConfig()` khong tham so, nen `incrementalCache` roi ve
 * mac dinh `"dummy"`. Khi do 42 trang da prerender luc build (HTML + RSC +
 * segment) khong bao gio duoc doc lai — moi request deu nap
 * `server-functions/default/handler.mjs` (~5,2 MB sau bundle) roi render lai
 * React tu dau. Isolate nguoi phai lam tat ca viec do trong tran 128 MB, tran
 * nay CO DINH o moi goi Cloudflare ke ca Paid.
 *
 * VI SAO CAN TEST NAY. Neu ai do go hai tuy chon duoi day, hoac doi `cf:build`
 * ve `opennextjs-cloudflare build` tran, thi KHONG CO LOI NAO XUAT HIEN. App
 * van chay, van dung — chi la lang le quay ve duong render dat tien va rui ro
 * 1102 quay lai. Hong lang le thi phai co test canh.
 *
 * Do duoc bang `wrangler dev` tren cung mot ban build, cung mot route,
 * isolate moi:
 *   - duong cu (server function): 354 ms cho request dau
 *   - duong moi (cache interception o tang middleware, 140 KB): 104 ms
 * Nhan biet tren response: `x-opennext-cache: HIT`, va KHONG co `x-opennext`
 * hay `x-powered-by: Next.js` (hai header do chi server function moi dat).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

const openNextConfig = read("../open-next.config.ts");
const pkg = JSON.parse(read("../package.json"));
const wrangler = read("../wrangler.jsonc");
const wranglerStaging = read("../wrangler.staging.jsonc");

test("open-next.config.ts phuc vu trang prerender tu Workers static assets", () => {
  // Khong duoc de `incrementalCache` roi ve mac dinh "dummy".
  assert.match(
    openNextConfig,
    /incremental-cache\/static-assets-incremental-cache/,
    "phai import override `static-assets-incremental-cache` (doc cache qua binding ASSETS, khong them KV/D1/R2)",
  );
  assert.match(
    openNextConfig,
    /defineCloudflareConfig\(\{/,
    "`defineCloudflareConfig()` khong tham so = incrementalCache \"dummy\" = render lai moi request",
  );
  assert.match(
    openNextConfig,
    /incrementalCache,/,
    "phai truyen `incrementalCache` vao defineCloudflareConfig",
  );
});

test("cache interception duoc bat de khong nap server function cho route tinh", () => {
  assert.match(
    openNextConfig,
    /enableCacheInterception:\s*true/,
    "thieu tuy chon nay thi tang routing khong tra thang HTML/RSC da prerender, va Worker van phai `import()` bundle 5,2 MB",
  );
});

test("KHONG khai them tai nguyen Cloudflare phai tra tien", () => {
  // Cache nam trong static assets da co san. Khai R2/KV/D1 la them thu phai
  // tra tien va phai bao tri ma khong duoc gi (khong ISR, khong revalidate).
  for (const forbidden of ["r2_buckets", "kv_namespaces", "d1_databases"]) {
    for (const [name, text] of [
      ["wrangler.jsonc", wrangler],
      ["wrangler.staging.jsonc", wranglerStaging],
    ]) {
      const declared = text
        .split(/\r?\n/)
        .filter((line) => !line.trim().startsWith("//"))
        .join("\n");
      assert.ok(
        !declared.includes(forbidden),
        `${name} khong duoc khai ${forbidden}`,
      );
    }
  }
});

test("binding ASSETS con nguyen o CA HAI cau hinh Worker", () => {
  // Mat binding nay la mat luon cache trang prerender, khong chi mat tep tinh.
  for (const [name, text] of [
    ["wrangler.jsonc", wrangler],
    ["wrangler.staging.jsonc", wranglerStaging],
  ]) {
    assert.match(text, /"binding":\s*"ASSETS"/, `${name} thieu binding ASSETS`);
    assert.match(
      text,
      /"directory":\s*"\.open-next\/assets"/,
      `${name} thieu thu muc assets`,
    );
  }
});

test("moi duong build deu chay buoc populateCache", () => {
  // `populateCache` la buoc sao `.open-next/cache/**` sang
  // `.open-next/assets/cdn-cgi/_next_cache/**`. No KHONG chay trong
  // `opennextjs-cloudflare build` — chi trong deploy/preview/upload. Duong
  // deploy staging dung `wrangler deploy` tran, nen buoc nay phai nam trong
  // `cf:build`.
  assert.match(
    pkg.scripts["cf:build"],
    /opennextjs-cloudflare populateCache local/,
    "cf:build phai tu populate cache, vi staging deploy bang `wrangler deploy` tran khong lam viec do",
  );

  // Va moi script khac phai di qua cf:build, dung goi
  // `opennextjs-cloudflare build` tran nua.
  for (const [name, cmd] of Object.entries(pkg.scripts)) {
    if (name === "cf:build" || !cmd.includes("opennextjs-cloudflare build")) {
      continue;
    }
    assert.fail(
      `script "${name}" goi \`opennextjs-cloudflare build\` tran — phai dung \`npm run cf:build\` de co buoc populateCache`,
    );
  }
});

test("KHONG bat run_worker_first", () => {
  // Mac dinh da la false (asset router bo qua Worker khi co tep khop). Bat len
  // se lam ca request tep tinh phai chay Worker.
  for (const [name, text] of [
    ["wrangler.jsonc", wrangler],
    ["wrangler.staging.jsonc", wranglerStaging],
  ]) {
    const declared = text
      .split(/\r?\n/)
      .filter((line) => !line.trim().startsWith("//"))
      .join("\n");
    assert.ok(
      !declared.includes("run_worker_first"),
      `${name} khong nen khai run_worker_first`,
    );
  }
});
