import { readFileSync } from "node:fs";
import { expect, test, type Locator, type Page } from "@playwright/test";

// Milestone 6: one run through the 4-minute demo script in README.md, a step per section,
// on the real data (DATA_SOURCE=real). Each step saves screenshots to docs/screenshots/demo/.
// Builder names change when the data is refreshed, so names are read off the page.
//
// Next keeps the page it leaves mounted but hidden (display: none): the search screen stays
// in the document behind the grid, and the grid behind the search screen after "New scan".
// Lookups go by role, which skips hidden content, and text lookups keep to what is visible.

const SHOTS = "docs/screenshots/demo";

const demo = JSON.parse(readFileSync("data/demo-searches.json", "utf8")) as { examples: { label: string; text: string }[] };
const searches = JSON.parse(readFileSync("data/searches.json", "utf8")) as {
  entries: Record<string, { text: string; criteria: { topic: string | null } }>;
};
const ml = demo.examples.find((e) => e.label === "ML intern, Toronto")!;
const rag = Object.values(searches.entries).find((e) => e.text === "Built a RAG pipeline")!;

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const firstName = (name: string) => name.trim().split(/\s+/)[0];

// Stable pixels, as in screens.spec.ts: finite animations (the card-to-entry morph, pop-ins,
// the radar, the shortlist sparks) are fast-forwarded to their end, endless ones are held
// at their start, and the mouse is parked so no hover state shows.
async function shot(page: Page, name: string) {
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `${SHOTS}/${name}.png`, animations: "disabled" });
}

/** A section of the Dex entry, by its heading. */
function section(page: Page, heading: string | RegExp): Locator {
  return page.locator("section", { has: page.getByRole("heading", { name: heading }) });
}

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test("the 4-minute demo, start to finish", async ({ page, request, baseURL }) => {
  const { source, scan } = await (await request.get("/api/scan")).json();
  test.skip(source !== "real", "the demo script runs on the real data");
  const total: number = scan.projectsChecked;

  const shown = (text: string | RegExp) => page.getByText(text).filter({ visible: true });
  const h1 = page.getByRole("heading", { level: 1 });
  // Revealed cards only: a silhouette is hidden from screen readers, so it has no role.
  const cards = page.getByRole("main").getByRole("article");
  const cardName = (card: Locator) => card.getByRole("heading", { level: 2 });
  // "k of N" between Prev and Next on a Dex entry.
  const position = page.getByRole("group", { name: "Flip through builders" });

  // Nothing is fetched live: every request the page makes stays on this server.
  const offsite: string[] = [];
  page.on("request", (r) => {
    if (!r.url().startsWith(baseURL!)) offsite.push(r.url());
  });

  await test.step("0:00 The search", async () => {
    await page.goto("/");
    await expect(shown(new RegExp(`^Scanning ${total} projects from ${scan.hackathons.length} hackathons?$`))).toBeVisible();
    await shot(page, "01-search");

    await page.getByRole("button", { name: ml.label }).click();
    await expect(page.getByRole("textbox")).toHaveValue(ml.text);
    await shot(page, "02-search-chip");

    // The chip's text is a cached Gemini parse, so Gemini isn't called.
    const parse = page.waitForResponse("**/api/parse");
    await page.getByRole("button", { name: /Start scan/ }).click();
    expect(await (await parse).json()).toMatchObject({ source: "gemini", cached: true });
    await page.waitForURL(/\/matches\?/);
  });

  await test.step("0:30 The scan replay", async () => {
    for (const chip of ["ML / AI", "Year 3", "Toronto", "Hackathon winner"]) {
      await expect(page.getByRole("button", { name: "Remove filter " + chip })).toBeVisible();
    }
    await expect(h1).toHaveText("Scouting for you…");
    await expect(shown(new RegExp(`^\\d+ / ${total}$`))).toBeVisible();
    // The progress panel moves through its three phases, in order.
    for (const phase of ["Reading Devpost projects", "Checking GitHub commits", "Comparing builders to your search"]) {
      await expect(shown(phase)).toBeVisible();
    }
    // A builder whose project hasn't come up yet is still a silhouette while the cards around it fill in.
    await page.waitForFunction(() => {
      const any = (selector: string) => Array.from(document.querySelectorAll(selector)).some((el) => el.checkVisibility());
      return any(".silhouette") && any("article .stretch-btn");
    });
    await shot(page, "03-scanning");

    await expect(shown(`Scan complete! ${total} projects checked.`)).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".silhouette")).toHaveCount(0);
  });

  const top = await test.step("1:00 The grid", async () => {
    await expect(h1).toHaveText(/^\d+ builders? found!$/);
    const found = (await h1.textContent())!.match(/\d+/)![0];
    const tabs = page.getByRole("group", { name: "Filter by type" }).getByRole("button");
    await expect(tabs.first()).toHaveAccessibleName(`All ${found}`);
    await expect(tabs.first()).toHaveAttribute("aria-pressed", "true");
    // A fresh window: nothing seen or shortlisted yet.
    await expect(shown(/^Seen 0$/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Shortlist, 0 builders" })).toBeVisible();
    await shot(page, "04-scan-complete");

    const firstCard = cardName(cards.first());
    const top = (await firstCard.textContent())!;

    // Dropping a filter re-ranks at once; Restore filters brings the ranking back.
    await page.getByRole("button", { name: "Remove filter Year 3" }).click();
    await expect(page.getByRole("button", { name: /^Remove filter / })).toHaveCount(3);
    await expect(page.getByRole("button", { name: "Restore filters" })).toBeVisible();
    await shot(page, "05-filter-removed");
    await page.getByRole("button", { name: "Restore filters" }).click();
    await expect(page.getByRole("button", { name: /^Remove filter / })).toHaveCount(4);
    await expect(firstCard).toHaveText(top);

    // A type tab shows only that type's builders. The smallest one fits on one page.
    const counts = (await tabs.allTextContents()).map((t) => Number(t.match(/\d+$/)![0]));
    const pick = counts.indexOf(Math.min(...counts.slice(1)), 1);
    const type = (await tabs.nth(pick).textContent())!.replace(/\d+$/, "").trim();
    await tabs.nth(pick).click();
    await expect(tabs.nth(pick)).toHaveAttribute("aria-pressed", "true");
    await expect(cards).toHaveCount(counts[pick]);
    await expect(cards.filter({ hasNotText: type })).toHaveCount(0);
    await shot(page, "06-type-tab");
    await tabs.first().click();
    await expect(tabs.first()).toHaveAttribute("aria-pressed", "true");
    await expect(firstCard).toHaveText(top);

    // Most wins puts the most prizes first; Best match brings the ranking back.
    const sort = page.getByLabel("Sort by");
    await sort.selectOption({ label: "Most wins" });
    await expect(async () => {
      const wins = await cards.evaluateAll((els) => els.map((el) => Number((el as HTMLElement).innerText.match(/(\d+)\s+Wins\b/)![1])));
      expect(wins.length).toBeGreaterThan(1);
      expect(wins).toEqual([...wins].sort((a, b) => b - a));
    }).toPass({ timeout: 15_000 });
    await shot(page, "07-sort-wins");
    await sort.selectOption({ label: "Best match" });
    await expect(firstCard).toHaveText(top);

    // Starring a card puts them on the header's Shortlist.
    await cards.first().getByRole("button", { name: `Add ${top} to shortlist` }).click();
    await expect(cards.first().getByRole("button", { name: `Remove ${top} from shortlist` })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Shortlist, 1 builder" })).toBeVisible();
    await shot(page, "08-shortlisted");
    return top;
  });

  await test.step("1:30 A Dex entry: why they fit, and effort", async () => {
    const score = (await cards.first().getByRole("img", { name: /^Match score \d+ percent$/ }).getAttribute("aria-label"))!;
    await cardName(cards.first()).getByRole("button").click();
    // The card grows into the Dex entry, and focus moves to the builder's name.
    await expect(h1).toHaveText(top);
    await expect(h1).toBeFocused();
    await expect(page.getByRole("img", { name: score, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /^All \d+ builders$/ })).toBeVisible();
    await expect(position.getByText(/^1 of \d+$/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Shortlisted!" })).toHaveAttribute("aria-pressed", "true");
    await expect(shown(/^Seen 1$/)).toBeVisible();

    // One row per filter, each saying how it matched and where that came from.
    const why = section(page, `Why ${firstName(top)} fits your search`);
    const rows = why.getByRole("listitem");
    await expect(rows).toHaveCount(4);
    await expect(rows).toContainText(["ML / AI", "Year 3", "Toronto", "Hackathon winner"]);
    for (const row of await rows.all()) {
      await expect(row.getByRole("img", { name: /^(Matches|Close|Does not match|Not listed)$/ })).toBeVisible();
      await expect(row).toContainText(/GitHub|Devpost|résumé|People Data Labs/);
    }
    const met = await why.getByRole("img", { name: "Matches", exact: true }).count();
    await expect(why.getByText(`${met} of 4 match`, { exact: true })).toBeVisible();
    await shot(page, "09-dex-entry");

    // Effort: points by area, each row naming the projects behind it.
    const board = section(page, "Trait board");
    await expect(board.getByRole("button", { name: "Effort", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(board.getByRole("img", { name: new RegExp(`^Effort hexagon for ${escapeRegExp(top)}: `) })).toBeVisible();
    await expect(board.getByText(/^From .+/).first()).toBeVisible();
    await expect(board.getByText(/^\d+ \/ 510 effort points$/)).toBeVisible();
    await board.scrollIntoViewIfNeeded();
    await shot(page, "10-evs");
  });

  const next = await test.step("2:00 Traits, field notes, signature projects", async () => {
    const first = firstName(top);
    const board = section(page, "Trait board");
    const ivs = board.getByRole("button", { name: "Traits", exact: true });
    await ivs.click();
    await expect(ivs).toHaveAttribute("aria-pressed", "true");
    await expect(board.getByText(/ nature$/)).toBeVisible();
    await expect(board.getByText(`How ${first} ranks against the ${scan.buildersFound} builders in this scan, from 0 to 31.`)).toBeVisible();
    await expect(board.getByRole("listitem")).toHaveCount(6);
    await expect(board.getByRole("listitem")).toContainText(["Ships demos", "Wins", "Ownership", "Teamwork", "Persistence", "Documentation"]);
    // Anything we couldn't find reads "Not listed" and says where we looked.
    const notes = section(page, "Field notes");
    await expect(notes.getByRole("definition").filter({ hasText: /^Not listed/ }).filter({ hasNotText: /Looked in .+\./ })).toHaveCount(0);
    await expect(shown(new RegExp(`^${escapeRegExp(first)} wrote \\d+%$`)).first()).toBeVisible();
    await board.scrollIntoViewIfNeeded();
    await shot(page, "11-ivs");

    // The arrow keys walk the ranked list.
    const next = (await page.getByRole("button", { name: /^Next: / }).getAttribute("aria-label"))!.replace(/^Next: #\d+ /, "");
    await page.keyboard.press("ArrowRight");
    await expect(h1).toHaveText(next);
    await expect(h1).toBeFocused();
    await expect(position.getByText(/^2 of \d+$/)).toBeVisible();
    await expect(shown(/^Seen 2$/)).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "12-next-builder");
    return next;
  });

  await test.step("2:30 Say hi", async () => {
    const sayHi = page.getByRole("button", { name: "Say hi" });
    await sayHi.click();
    const draft = page.getByRole("region", { name: "Outreach draft" });
    await expect(draft.getByRole("heading", { name: `Say hi to ${firstName(next)}` })).toBeFocused();
    await expect(draft.getByText(/^Subject: .+/)).toBeVisible();
    for (const blank of ["[ROLE]", "[COMPANY]", "[TEAM OR PRODUCT]"]) {
      await expect(draft).toContainText(blank);
    }
    await draft.getByRole("button", { name: "Copy email" }).click();
    await expect(draft.getByRole("button", { name: "Copied!" })).toBeVisible();
    await expect(draft.getByRole("status")).toHaveText("Email copied.");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(new RegExp(`^Subject: .+\\n\\nHi ${escapeRegExp(firstName(next))},\\n`));
    await shot(page, "13-say-hi");

    // Escape closes the innermost thing first: the draft, then the Dex entry.
    await page.keyboard.press("Escape");
    await expect(draft).toHaveCount(0);
    await expect(sayHi).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(h1).toHaveText(/^\d+ builders? found!$/);
    await expect(cardName(cards.first()).getByRole("button")).toBeFocused();
    await expect(cardName(cards.first())).toHaveText(top);
    // Back where it was: the scan doesn't replay, and the shortlist is kept.
    await expect(shown(`Scan complete! ${total} projects checked.`)).toBeVisible();
    await expect(page.getByRole("button", { name: "Shortlist, 1 builder" })).toBeVisible();
    await shot(page, "14-back-to-grid");
  });

  await test.step("3:00 A topic search", async () => {
    await page.getByRole("link", { name: "New scan" }).click();
    await expect(page.getByRole("heading", { name: "Who are you hiring?" })).toBeVisible();
    await page.getByRole("textbox").fill(rag.text);
    await shot(page, "15-new-scan");

    const parse = page.waitForResponse("**/api/parse");
    await page.getByRole("button", { name: /Start scan/ }).click();
    expect(await (await parse).json()).toMatchObject({ source: "gemini", cached: true });
    await page.waitForURL(/\/matches\?/);
    for (const chip of ["ML / AI", "Backend", rag.criteria.topic!]) {
      await expect(page.getByRole("button", { name: "Remove filter " + chip })).toBeVisible();
    }
    // The shortlist carries over to the new search.
    await expect(page.getByRole("button", { name: "Shortlist, 1 builder" })).toBeVisible();
    // No "Couldn't check projects for this topic" after it: the topic search ran.
    await expect(shown(new RegExp(`^Scan complete! ${total} projects checked\\.$`))).toBeVisible({ timeout: 20_000 });
    await shot(page, "16-topic-grid");

    await cardName(cards.first()).getByRole("button").click();
    const topicRow = section(page, /^Why .+ fits your search$/).getByRole("listitem").filter({ hasText: rag.criteria.topic! });
    await expect(topicRow.getByText(/^Built .+ \(wrote \d+%\)$/)).toBeVisible();
    await expect(topicRow.getByRole("img", { name: "Matches", exact: true })).toBeVisible();
    await shot(page, "17-topic-entry");
  });

  await test.step("3:30 Close on trust", async () => {
    const notes = section(page, "Field notes");
    await notes.scrollIntoViewIfNeeded();
    await expect(notes.getByText(/(linked from .+'s own Devpost profile, so this is the right person|through their Devpost team, not by name across sites)\.$/)).toBeVisible();
    await shot(page, "18-trust");
  });

  expect(offsite, "requests that left this server").toEqual([]);
});
