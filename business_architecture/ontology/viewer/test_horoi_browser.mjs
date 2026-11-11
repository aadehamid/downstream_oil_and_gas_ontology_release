// Run: node test_horoi_browser.mjs <path to horoi_viewer/index.html>
// Needs the playwright-core package where Node can find it and a Chrome or Chromium (CHROME_PATH names it).
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright-core");

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
try {
  assert.ok(process.argv[2], "Pass the path to horoi_viewer/index.html");
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  // The page must work offline: any request that leaves the file system is counted and stopped.
  let network = 0;
  await page.route(/^https?:/, (route) => {
    network++;
    return route.abort();
  });
  const url = pathToFileURL(resolve(process.argv[2])).href;
  await page.goto(url);

  // The release name is on every view, in the bar under the header.
  assert.equal(await page.locator("#release-scope").innerText(), "KPI Store 1.1 · All ontology modules");

  // The overview lists the thirteen modules, technical-graph at 1.1.0.
  const tiles = page.locator(".module-directory a.tile");
  assert.equal(await tiles.count(), 13);
  assert.match(await page.locator(".module-directory a.tile.technical-graph").innerText(), /technical-graph · 1\.1\.0/i);

  // Release and coverage names the release and no commit.
  await page.goto(url + "#about");
  const about = await page.locator("#content").innerText();
  assert.match(about, /every current ontology module of KPI Store 1\.1\./);
  assert.match(about, /release packages of KPI Store 1\.1\./);
  assert.doesNotMatch(about, /commit|undefined|EPM/);
  assert.doesNotMatch(await page.content().then((html) => html.split('<script id="ontology-data"')[0]), /EPM 1\.0/);

  // Search finds a term that technical-graph 1.1.0 added, and its page opens.
  await page.goto(url + "#browse");
  await page.locator("#search").fill("replaces");
  await page.locator("#module-filter").selectOption("technical-graph");
  await page.locator("#results li a").first().waitFor();
  assert.match(await page.locator("#result-count").innerText(), /\d/);
  const hit = page.locator('#results a[href="#term=https%3A%2F%2Fw3id.org%2Fmpc%2Fontology%2Fmodules%2Ftechnical-graph%2Freplaces"]');
  assert.equal(await hit.count(), 1);
  await hit.click();
  await page.locator("#content h1").waitFor();
  assert.equal(await page.locator("#content h1").innerText(), "replaces");
  assert.match(await page.locator("#content").innerText(), /https:\/\/w3id\.org\/mpc\/ontology\/modules\/technical-graph\/replaces/);
  assert.match(await page.locator("#content").innerText(), /What points to this term/);

  // A module page, a term of another module, and the narrow layout.
  await page.goto(url + "#module=technical-graph");
  assert.match(await page.locator("#content").innerText(), /1\.1\.0/);
  await page.goto(url + "#browse?q=customer+account&module=party");
  await page.locator("#results li a").first().click();
  await page.locator("#content h1").waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url + "#overview");
  assert.equal(await page.locator("#release-scope").innerText(), "KPI Store 1.1 · All ontology modules");
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  const shots = mkdtempSync(join(tmpdir(), "kpi-store-reference-"));
  await page.screenshot({ path: join(shots, "overview-390.png") });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: join(shots, "overview-1440.png") });
  await page.goto(url + "#about");
  await page.screenshot({ path: join(shots, "about-1440.png") });

  assert.deepEqual(errors, []);
  assert.equal(network, 0);
  console.log(JSON.stringify({ release: "KPI Store 1.1", modules: 13, technicalGraph: "1.1.0", search: true, termPage: true, mobile: true, pageErrors: errors, networkRequests: network, screenshots: shots }));
} finally {
  await browser.close();
}
