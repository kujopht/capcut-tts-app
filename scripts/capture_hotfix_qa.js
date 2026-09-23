const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join(__dirname, '../web/node_modules/playwright'));

const OUT_DIR = 'C:/Users/nguye/.agy-sessions/acc3/.gemini/antigravity-cli/brain/93db2db7-58cf-4238-9fb2-3fb8b37e597a/screenshots_hotfix';
fs.mkdirSync(OUT_DIR, { recursive: true });

const prefix = process.argv[2] || 'before';
const targetUrl = process.argv[3] || 'https://fanfic.world';

const VIEWPORTS = [
  { name: `${prefix}_1600x900`, width: 1600, height: 900 },
  { name: `${prefix}_1440x900`, width: 1440, height: 900 },
  { name: `${prefix}_1366x768`, width: 1366, height: 768 },
  { name: `${prefix}_390x844`, width: 390, height: 844 },
];

async function run() {
  console.log(`Capturing ${prefix} screenshots for ${targetUrl}...`);
  const browser = await chromium.launch({ headless: true });

  for (const vp of VIEWPORTS) {
    try {
      console.log(`Capturing ${vp.name} (${vp.width}x${vp.height})...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForSelector('.lib-card, .home-story-row, .novel-head', { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2000);
      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved: ${outPath}`);
      await context.close();
    } catch (err) {
      console.error(`Failed ${vp.name}:`, err.message);
    }
  }

  await browser.close();
  console.log(`Done capturing ${prefix}.`);
}

run();
