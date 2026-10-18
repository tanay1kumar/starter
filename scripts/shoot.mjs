// Screenshot the design file and/or the running app with Playwright, for side-by-side checks.
//
//   node scripts/shoot.mjs design            -> shots of design/talent-dex-v3.html
//   node scripts/shoot.mjs app [baseUrl]     -> shots of the running app (default http://localhost:3000)
//   OUT=dir WIDTH=1440 node scripts/shoot.mjs ...
//
// Shots: <target>-grid.png (scan finished), <target>-profile.png (first card opened),
// <target>-profile-iv.png (IVs tab), <target>-profile-draft.png ("Say hi" open),
// <target>-grid-scanning.png (mid-scan).

import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = process.argv[2] || "app";
const base = process.argv[3] || "http://localhost:3000";
const out = path.resolve(process.env.OUT || path.join(root, "test-results", "shots"));
const width = +(process.env.WIDTH || 1440);
const height = +(process.env.HEIGHT || 1000);
fs.mkdirSync(out, { recursive: true });

const url = target === "design" ? pathToFileURL(path.join(root, "design", "talent-dex-v3.html")).href : base + (process.env.APP_PATH || "/matches");
const tag = (process.env.TAG || target) + (width !== 1440 ? "-" + width : "");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
page.on("pageerror", (e) => console.error("[pageerror]", e.message));

await page.goto(url, { waitUntil: "load" });
await page.waitForTimeout(2300);
await page.screenshot({ path: path.join(out, tag + "-grid-scanning.png"), fullPage: false });
await page.waitForTimeout(4200);
await page.mouse.move(0, 0);
await page.screenshot({ path: path.join(out, tag + "-grid.png"), fullPage: true });

const nameButton = page.locator("article h2 button").first();
await nameButton.click();
await page.waitForTimeout(1400);
await page.mouse.move(0, 0);
await page.screenshot({ path: path.join(out, tag + "-profile.png"), fullPage: true });

await page.getByRole("button", { name: "IVs · Traits" }).click();
await page.waitForTimeout(900);
await page.screenshot({ path: path.join(out, tag + "-profile-iv.png"), fullPage: true });

await page.getByRole("button", { name: /Say hi/ }).click();
await page.waitForTimeout(900);
await page.screenshot({ path: path.join(out, tag + "-profile-draft.png"), fullPage: false });

await browser.close();
console.log("saved shots to", out);
