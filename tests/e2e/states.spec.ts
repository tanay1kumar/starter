import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Milestone 6: empty, error and loading states. Failures are simulated with
// page.route, so this runs on either dataset (one topic test needs DATA_SOURCE=real).

async function scanDone(page: Page) {
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
}

const wait = (ms: number) => new Promise((done) => setTimeout(done, ms));

// "Built a RAG pipeline" as a topic-only search, with the cached topic sentence, so the
// real topic search answers from the vectors made ahead of time (no model load).
const searches = JSON.parse(readFileSync("data/searches.json", "utf8")) as {
  entries: Record<string, { text: string; criteria: { topic: string | null; topicQuery: string | null } }>;
};
const rag = Object.values(searches.entries).find((e) => e.text === "Built a RAG pipeline")!.criteria;
const RAG_URL = "/matches?" + new URLSearchParams({ topic: rag.topic!, tq: rag.topicQuery! }).toString();

const TOPIC_500 = { status: 500, json: { error: "Couldn't run the topic search." } };
/** Cards shown before "Show more" (PAGE_SIZE in lib/viewmodel.ts). */
const PAGE = 24;

type Row = { types: string[]; typeProjects: Record<string, number> };
/** Builders with card type `u` that a search for type `t` finds (they have `t` code). */
const overlap = (rows: Row[], t: string, u: string) => rows.filter((b) => b.types.includes(u) && b.typeProjects[t] > 0);

test("builders that fail to load say why, and Try again recovers", async ({ page }) => {
  let fail = true;
  await page.route("**/api/builders", (route) => (fail ? route.abort("internetdisconnected") : route.continue()));
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: "Something went wrong" })).toBeVisible();
  await expect(page.getByText("Couldn't reach Talent Dex. Check your connection and try again.")).toBeVisible();

  // It fails again: focus comes back to the button that went away while loading.
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("button", { name: "Try again" })).toBeFocused();

  // It works: the button is gone, so focus moves to the grid's headline.
  fail = false;
  await page.getByRole("button", { name: "Try again" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-grid-headline]")).toBeFocused();
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
});

test("a server error or a broken answer is an error, not an endless loading frame", async ({ page }) => {
  let answer: "500" | "bare 500" | "junk" = "500";
  await page.route("**/api/builders", (route) =>
    answer === "500"
      ? route.fulfill({ status: 500, json: { error: "Couldn't read the builders data." } })
      : answer === "bare 500"
        ? route.fulfill({ status: 500, json: {} })
        : route.fulfill({ status: 200, json: { version: 1 } }),
  );
  await page.goto("/matches");
  await expect(page.getByText("Couldn't read the builders data.")).toBeVisible();
  // No message from the server: a plain line, never a status code.
  answer = "bare 500";
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("Couldn't load builders. Try again.")).toBeVisible();
  answer = "junk";
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Something went wrong" })).toBeVisible();
  await expect(page.getByText("Couldn't read the builders data.")).toBeVisible();
});

test("a slow load shows the loading line", async ({ page }) => {
  await page.route("**/api/builders", async (route) => {
    await wait(1500);
    await route.continue();
  });
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: "Scouting for you…" })).toBeVisible();
  await expect(page.getByText("Loading builders")).toBeVisible();
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
});

test("a search that finds nobody says so plainly", async ({ page }) => {
  await page.route("**/api/builders", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), builders: [] } });
  });
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: "No builders found" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("No builders match this search yet. Try removing a filter.")).toBeVisible();
  await expect(page.locator("p[role=status]")).toHaveText(/^Scan finished: \d+ projects checked\. Found no builders\.$/);
});

test("a topic that can't be checked says so, and hides nobody", async ({ page }) => {
  await page.route("**/api/topic", (route) => route.fulfill({ status: 500, json: { error: "Couldn't run the topic search." } }));
  await page.goto("/matches?topic=RAG+pipeline");
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/^Scan complete! \d+ projects checked\. Couldn't check projects for this topic\.$/)).toBeVisible();
  await page.locator("article h2 button").first().click();
  await expect(page.getByText("Couldn't check projects for this topic", { exact: true })).toBeVisible();
});

test("a slow topic check says what it's waiting for", async ({ page }) => {
  // Slow only once the builders are in, so the wait is for the topic alone.
  const builders = page.waitForResponse("**/api/builders");
  await page.route("**/api/topic", async (route) => {
    await builders;
    await wait(1500);
    await route.continue();
  });
  await page.goto(RAG_URL);
  await expect(page.getByRole("heading", { name: "Scouting for you…" })).toBeVisible();
  // The builders are in; only the topic is still being checked.
  await expect(page.getByText("Checking projects for this topic…")).toBeVisible();
  await expect(page.getByText("Loading builders")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
});

test("a failed topic check has its own Try again, which checks only the topic", async ({ page }) => {
  let topicCalls = 0;
  let builderCalls = 0;
  let slow = false;
  await page.route("**/api/builders", (route) => {
    builderCalls += 1;
    return route.continue();
  });
  await page.route("**/api/topic", async (route) => {
    topicCalls += 1;
    if (slow) await wait(1000);
    await route.fulfill(TOPIC_500);
  });
  await page.goto(RAG_URL);
  const done = page.getByText(/^Scan complete! \d+ projects checked\./);
  await expect(done).toHaveText(/Couldn't check projects for this topic\.$/, { timeout: 20_000 });
  const calls = { topic: topicCalls, builders: builderCalls };
  const retry = page.getByRole("button", { name: "Try again" });
  slow = true;
  await retry.click();
  // The finished scan stays; the panel says what's happening instead of replaying.
  await expect(done).toHaveText(/Checking projects for this topic…$/);
  await expect(retry).toHaveCount(0);
  // It failed again: focus comes back to the button.
  await expect(retry).toBeFocused();
  await expect(done).toHaveText(/Couldn't check projects for this topic\.$/);
  expect(topicCalls).toBe(calls.topic + 1);
  expect(builderCalls).toBe(calls.builders);
});

test("Try again on a failed topic check ranks by the topic once it works", async ({ page, request }) => {
  const { source } = await (await request.get("/api/scan")).json();
  test.skip(source !== "real", "topic search runs on the real data");
  let fail = true;
  await page.route("**/api/topic", (route) => (fail ? route.fulfill(TOPIC_500) : route.continue()));
  await page.goto(RAG_URL);
  await expect(page.getByText(/^Scan complete! \d+ projects checked\. Couldn't check projects for this topic\.$/)).toBeVisible({ timeout: 20_000 });
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  // The button is gone: focus moves to the headline, which now counts the topic's builders.
  await expect(page.locator("[data-grid-headline]")).toBeFocused();
  await expect(page.getByText(/^Scan complete! \d+ projects checked\.$/)).toBeVisible();
  await expect(page.locator("p[role=status]")).toHaveText(/^Scan finished: \d+ projects checked\. Found (\d+ builders?|no builders)\.$/);
  await page.locator("article h2 button").first().click();
  const row = page
    .locator("section", { has: page.getByRole("heading", { name: /fits your search$/ }) })
    .getByRole("listitem")
    .filter({ hasText: rag.topic! });
  await expect(row.getByText(/^(Built .+ \(wrote \d+%\)|Wrote \d+% of .+|.+ is related( \(wrote \d+%\))?)$/)).toBeVisible();
});

test("the header's Shortlist button shows the shortlist, and an empty one leads back to everyone", async ({ page }) => {
  await scanDone(page);
  const toggle = page.getByRole("button", { name: /^Shortlist, \d+ builders?$/ });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  const star = page.locator("article .star").first();
  if ((await star.getAttribute("aria-pressed")) !== "true") await star.click();
  const count = Number((await toggle.getAttribute("aria-label"))!.match(/\d+/)![0]);

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("article[data-id]")).toHaveCount(count);
  await expect(page.locator("p[role=status]")).toHaveText(`Showing your shortlist: ${count} builder${count === 1 ? "" : "s"}.`);

  // Taking everyone off from the keyboard: focus moves to the next star, then to the toggle.
  for (let i = 0; i < count; i++) {
    await page.locator("article .star").first().focus();
    await page.keyboard.press("Enter");
  }
  await expect(page.getByText("No one on your shortlist yet.")).toBeVisible();
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAccessibleName("Shortlist, 0 builders");

  // "Show all builders" turns the view off and hands focus to the headline.
  await page.getByRole("button", { name: "Show all builders" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-grid-headline]")).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: /^All \d+$/ })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Show all builders" })).toHaveCount(0);

  // A shortlist of one: the open entry's back button says "builder", not "builders".
  await page.locator("article .star").first().click();
  await toggle.click();
  await page.locator("article h2 button").first().click();
  await expect(page.getByRole("button", { name: "All 1 builder", exact: true })).toBeVisible();
});

test("taking the open builder off the shortlist keeps their place until the entry closes", async ({ page }) => {
  await scanDone(page);
  const stars = page.locator("article .star");
  for (const i of [0, 1]) {
    if ((await stars.nth(i).getAttribute("aria-pressed")) !== "true") await stars.nth(i).click();
  }
  const toggle = page.getByRole("button", { name: /^Shortlist, \d+ builders?$/ });
  await toggle.click();
  const count = await page.locator("article[data-id]").count();
  expect(count).toBeGreaterThan(1);
  const second = (await page.locator("article h2 button").nth(1).textContent())!.trim();

  await page.locator("article h2 button").first().click();
  const position = page.getByRole("group", { name: "Flip through builders" });
  await expect(position.getByText(`1 of ${count}`, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Shortlisted!" }).click();
  await expect(page.getByRole("button", { name: "Shortlist", exact: true })).toHaveAttribute("aria-pressed", "false");
  // Still in the list while open: same place, same back label, Next and → still work.
  await expect(position.getByText(`1 of ${count}`, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: `All ${count} builders` })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Next: / })).toBeEnabled();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(second);

  // Closed, they leave the shortlist view.
  await page.keyboard.press("Escape");
  await expect(page.locator("article[data-id]")).toHaveCount(count - 1);
  await expect(page.locator("article h2 button").first()).toBeFocused();
  await expect(page.locator("article h2 button").first()).toHaveText(second);
});

test("the picked type tab stays pressed when a chip change or a replay empties it", async ({ page, request }) => {
  // Search one type (t) that finds nobody of another type (u): taking the t chip off adds the
  // u tab, and "Restore filters" empties it again. The pair comes from the data; when every pair
  // overlaps (a newer run can), the route takes t code off the fewest builders to make one.
  const { builders } = (await (await request.get("/api/builders")).json()) as { builders: Row[] };
  const keys = Object.keys(builders[0].typeProjects);
  const pair = keys
    .flatMap((t) =>
      keys
        .filter((u) => u !== t && builders.some((b) => b.types.includes(u)) && builders.some((b) => !b.types.includes(u) && b.typeProjects[t] > 0))
        .map((u) => ({ t, u, changed: overlap(builders, t, u).length })),
    )
    .sort((a, b) => a.changed - b.changed)[0];
  expect(pair, "a type search that can leave out a whole type").toBeDefined();
  await page.route("**/api/builders", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    for (const b of overlap(data.builders, pair.t, pair.u)) b.typeProjects[pair.t] = 0;
    await route.fulfill({ response, json: data });
  });
  await page.goto("/matches?types=" + pair.t);
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });

  const group = page.getByRole("group", { name: "Filter by type" });
  const labels = async () => (await group.getByRole("button").allTextContents()).map((s) => s.replace(/\d+$/, ""));
  const before = await labels();
  const chip = page.getByRole("button", { name: /^Remove filter / });
  await chip.click();
  await expect(page.getByRole("button", { name: "Restore filters" })).toBeVisible();
  const pick = (await labels()).find((n) => !before.includes(n)) ?? "";
  expect(pick, "taking the chip off adds a tab").not.toBe("");
  const tab = group.getByRole("button", { name: new RegExp(`^${pick} \\d+$`) });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-pressed", "true");

  // Restore filters empties the tab: it stays pressed, at 0, and the grid says why.
  // (These checks can't pass on a tab that went away: a tab only comes back with builders.)
  const pressed = group.locator("[aria-pressed=true]");
  await page.getByRole("button", { name: "Restore filters" }).click();
  await expect(pressed).toHaveText([pick + "0"]);
  await expect(page.locator("article[data-id]")).toHaveCount(0);
  await expect(page.getByText("No builders of this type yet. Try another tab!")).toBeVisible();

  // A replay starts from no cards: the tab stays pressed at 0 with skeleton cards for the
  // builders to come, then fills in as the scan goes.
  await chip.click();
  await expect(tab).toHaveText(new RegExp(`^${pick}[1-9]\\d*$`));
  const total = Number((await tab.textContent())!.match(/\d+$/)![0]);
  await page.getByRole("button", { name: "Run the scan again" }).click();
  await expect(pressed).toHaveText([pick + "0"]);
  await expect(page.getByRole("main").locator("[data-skeleton]")).toHaveCount(Math.min(3, total));
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
  await expect(pressed).toHaveText([pick + total]);
  await expect(page.locator("article[data-id]")).toHaveCount(Math.min(total, PAGE));
});

test("a copy the browser refuses says so instead of claiming it worked", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", { value: { writeText: () => Promise.reject(new Error("denied")) } });
    document.execCommand = () => false;
  });
  await scanDone(page);
  await page.locator("article h2 button").first().click();
  await page.getByRole("button", { name: "Say hi" }).click();
  await page.getByRole("button", { name: "Copy email" }).click();
  await expect(page.getByRole("button", { name: "Couldn't copy" })).toBeVisible();
  await expect(page.locator("#say-hi-draft").getByRole("status")).toHaveText("Couldn't copy the email. Select the text to copy it yourself.");
});

test("a builder with no projects gets a plain empty state", async ({ page }) => {
  await page.route("**/api/builders", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    for (const b of data.builders) b.projects = [];
    await route.fulfill({ response, json: data });
  });
  await scanDone(page);
  await page.locator("article h2 button").first().click();
  await expect(page.getByText("No projects to show yet. Looked in Devpost.")).toBeVisible();
  await page.getByRole("button", { name: "Say hi" }).click();
  await expect(page.getByText("Subject: Your hackathon builds")).toBeVisible();
});

test("missing facts read Not listed and say where we looked", async ({ page }) => {
  await page.route("**/api/builders", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const missing = { value: null, source: null, looked: ["Devpost"] };
    for (const b of data.builders) {
      Object.assign(b, { school: missing, schoolFull: missing, program: missing, grad: missing, year: missing, city: missing, lastActive: missing });
      Object.assign(b, { repos: null, links: { ...b.links, github: null, linkedin: null } });
    }
    await route.fulfill({ response, json: data });
  });
  await scanDone(page);
  const card = page.locator("article[data-id]").first();
  await expect(card.getByText("School, year and city not listed")).toBeVisible();
  await expect(card.getByText(/^Not listed/)).toBeVisible();
  await card.locator(".stretch-btn").click();
  await expect(page.locator("dd").filter({ hasText: /^Not listedLooked in Devpost\.$/ })).toHaveCount(4);
  await expect(page.getByText("GitHub: Not linked on Devpost")).toBeVisible();
  await expect(page.getByText("LinkedIn: Not linked on Devpost")).toBeVisible();
  await expect(page.getByText(/^Code was matched to .+ through their Devpost team, not by name across sites\.$/)).toBeVisible();
});

test("screen 0 explains a failed search and stays ready to try again", async ({ page }) => {
  let parse: "500" | "down" = "500";
  await page.route("**/api/parse", (route) =>
    parse === "500" ? route.fulfill({ status: 500, json: { error: "Couldn't read your search. Try again." } }) : route.abort("connectionrefused"),
  );
  await page.goto("/");
  await page.getByRole("textbox").fill("ML intern in Toronto");
  await page.getByRole("button", { name: /Start scan/ }).click();
  await expect(page.locator("#hiring-error")).toHaveText("Couldn't read your search. Try again.");
  parse = "down";
  await page.getByRole("button", { name: /Start scan/ }).click();
  await expect(page.locator("#hiring-error")).toHaveText("Couldn't reach Talent Dex. Check your connection and try again.");
  await expect(page.getByRole("textbox")).toHaveValue("ML intern in Toronto");
});

test("Reading your search… shows only once the parse is slow", async ({ page }) => {
  await page.route("**/api/parse", async (route) => {
    await wait(1500);
    await route.continue();
  });
  await page.goto("/");
  await page.getByRole("textbox").fill("ML intern in Toronto");
  const start = page.locator("button[type=submit]");
  await start.click();
  expect(await start.textContent()).toBe("Start scan");
  await expect(start).toHaveText("Reading your search…");
  await page.waitForURL(/\/matches\?/);
});
