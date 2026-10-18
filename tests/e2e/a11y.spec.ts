import { expect, test, type Page } from "@playwright/test";

// Milestone 6: keyboard, focus and reduced motion. Runs on either dataset.

async function scanDone(page: Page) {
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
}

/** Press Tab until a card's name button has focus; returns that builder's id. */
async function tabToCard(page: Page): Promise<string> {
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press("Tab");
    const id = await page.evaluate(() => {
      const el = document.activeElement;
      return el?.classList.contains("stretch-btn") ? (el.closest("article")?.getAttribute("data-id") ?? null) : null;
    });
    if (id) return id;
  }
  throw new Error("Tab never reached a card");
}

/** Press Tab until `target` has focus. */
async function tabTo(page: Page, target: ReturnType<Page["locator"]>, max = 10) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement)) return;
  }
  throw new Error("Tab never reached " + target.toString());
}

/** Every Tab stop on the page, in order, with its focus outline. Stops when focus leaves the page or wraps. */
async function tabStops(page: Page, max = 140) {
  const stops: { name: string; outline: string }[] = [];
  let first: string | null = null;
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const stop = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      el.dataset.e2eStop ||= String(Math.random());
      const cs = getComputedStyle(el);
      return {
        key: el.dataset.e2eStop,
        name: (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().replace(/\s+/g, " "),
        outline: cs.outlineStyle + " " + cs.outlineWidth,
      };
    });
    if (!stop || stop.key === first) break;
    first ??= stop.key;
    stops.push({ name: stop.name, outline: stop.outline });
  }
  return stops;
}

/** Animations still in play two frames from now (a CSS animation cut short by reduced motion is over by then). */
function liveAnimations(page: Page) {
  return page.evaluate(
    () =>
      new Promise<string[]>((done) =>
        requestAnimationFrame(() =>
          requestAnimationFrame(() =>
            done(document.getAnimations().map((a) => a.constructor.name + (a instanceof CSSAnimation ? ":" + a.animationName : ""))),
          ),
        ),
      ),
  );
}

test("keyboard only: Tab to a card, Enter opens its Dex entry, Escape returns to the card", async ({ page }) => {
  await scanDone(page);
  const id = await tabToCard(page);
  const card = page.locator(`article[data-id="${id}"] .stretch-btn`);
  const name = (await card.textContent())!.trim();

  await page.keyboard.press("Enter");
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveText(name);
  await expect(heading).toBeFocused();
  await expect(page.getByRole("heading", { name: /fits your search/ })).toBeVisible();

  // The arrow keys flip to the next builder, and focus follows their name.
  if (await page.getByRole("button", { name: /^Next: / }).isEnabled()) {
    await page.keyboard.press("ArrowRight");
    await expect(heading).not.toHaveText(name);
    await expect(heading).toBeFocused();
  }

  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible();
  await expect(card).toBeFocused();
});

test.describe("the Say hi draft", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("takes focus when opened, doesn't trap it, and Escape returns it to the button", async ({ page }) => {
    await scanDone(page);
    const id = await tabToCard(page);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1 })).toBeFocused();

    const sayHi = page.getByRole("button", { name: "Say hi" });
    await tabTo(page, sayHi);
    await page.keyboard.press("Enter");
    const draftHeading = page.getByRole("heading", { name: /^Say hi to / });
    await expect(draftHeading).toBeFocused();
    await expect(page.getByRole("button", { name: "Hide draft" })).toHaveAttribute("aria-expanded", "true");

    // Copy works from the keyboard, and the result is read out.
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Copy email" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Copied!" })).toBeVisible();
    await expect(page.locator("#say-hi-draft").getByRole("status")).toHaveText("Email copied.");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/^Subject: .+\n\nHi /);

    // Not a trap: the next Tab leaves the draft.
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest("#say-hi-draft"))).toBe(false);

    await page.keyboard.press("Escape");
    await expect(draftHeading).toHaveCount(0);
    await expect(sayHi).toBeFocused();
    await expect(sayHi).toHaveAttribute("aria-expanded", "false");

    // The next Escape closes the Dex entry and lands on the card again.
    await page.keyboard.press("Escape");
    await expect(page.locator(`article[data-id="${id}"] .stretch-btn`)).toBeFocused();
  });
});

test("every control on the three screens shows the focus ring", async ({ page }) => {
  await page.goto("/");
  const search = await tabStops(page);
  expect(search.map((s) => s.name)).toEqual(expect.arrayContaining(["Starter", "ML intern, Toronto", "Start scan"]));

  await scanDone(page);
  await page.mouse.move(0, 0);
  const grid = await tabStops(page);
  const names = grid.map((s) => s.name);
  for (const want of [/^Shortlist, \d+ builders?$/, /^New scan$/, /^Remove filter /, /^Run the scan again$/, /^All\d+$/, /to shortlist$/]) {
    expect(names.some((n) => want.test(n)), String(want)).toBe(true);
  }

  await page.locator("article h2 button").first().click();
  await expect(page.getByRole("heading", { level: 1 })).toBeFocused();
  await page.getByRole("button", { name: "Say hi" }).click();
  // Opening the draft put focus inside it; walk the whole entry from the top instead.
  await page.getByRole("link", { name: "Starter" }).focus();
  const entry = await tabStops(page);
  for (const want of [/^All \d+ builders$/, /^Shortlist/, /^Hide draft$/, /^Copy email$/, /^Effort$/, /^Traits$/]) {
    expect(entry.map((s) => s.name).some((n) => want.test(n)), String(want)).toBe(true);
  }

  for (const stop of [...search, ...grid, ...entry]) {
    expect(stop.outline, stop.name).toBe("solid 3px");
  }
});

test("removing filters with the keyboard keeps focus in the chip row", async ({ page }) => {
  await scanDone(page);
  await page.getByRole("button", { name: "Remove filter Year 3" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Remove filter Toronto" })).toBeFocused();
  // The last chip hands focus back to the one before it.
  await page.getByRole("button", { name: "Remove filter Hackathon winner" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Remove filter Toronto" })).toBeFocused();
  await page.getByRole("button", { name: "Restore filters" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Remove filter ML / AI" })).toBeFocused();
  await expect(page.getByRole("button", { name: /^Remove filter / })).toHaveCount(4);
});

test("Show more moves focus to the first card it adds", async ({ page }) => {
  await scanDone(page);
  const more = page.getByRole("button", { name: /^Show \d+ more builders?$/ });
  test.skip((await more.count()) === 0, "needs more than one page of builders (DATA_SOURCE=real)");
  const before = await page.locator("article[data-id]").count();
  await more.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("article[data-id]").nth(before).locator(".stretch-btn")).toBeFocused();
});

test("the scan's status line announces the start and the finish, not every tick", async ({ page }) => {
  await page.goto("/matches");
  const status = page.locator("p[role=status]");
  await expect(status).toHaveText(/^Scan started\. Checking \d+ projects\.$/);
  const line = await status.textContent();
  const counter = page.getByText(/^\d+ \/ \d+$/);
  const first = await counter.textContent();
  await expect(counter).not.toHaveText(first!);
  // The counter moved; the status line did not.
  await expect(status).toHaveText(line!);
  // The ticking counter itself is not a live region.
  await expect(page.locator("[aria-live], [role=status], [role=alert]").filter({ hasText: /\d+ \/ \d+/ })).toHaveCount(0);
  // "Found", like the headline ("N builders found!"), but worded so that text lookups for the headline miss it.
  await expect(status).toHaveText(/^Scan finished: \d+ projects checked\. Found (\d+ builders?|no builders)\.$/, { timeout: 20_000 });
});

test.describe("reduced motion", () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
  });

  test("a Dex entry opens and flips without the morph, the slide or the sparks", async ({ page }) => {
    await scanDone(page);
    await page.locator("article h2 button").first().click();
    await expect(page.getByRole("heading", { level: 1 })).toBeFocused();
    expect(await liveAnimations(page)).toEqual([]);

    if (await page.getByRole("button", { name: /^Next: / }).isEnabled()) {
      await page.keyboard.press("ArrowRight");
      expect(await liveAnimations(page)).toEqual([]);
    }

    const shortlist = page.getByRole("button", { name: /^Shortlist(ed!)?$/ });
    if ((await shortlist.getAttribute("aria-pressed")) === "true") await shortlist.click();
    await shortlist.click();
    await expect(shortlist).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".burst")).toHaveCount(0);
    expect(await liveAnimations(page)).toEqual([]);
  });

  test("the scan still counts and reveals every card, without the sweep", async ({ page }) => {
    await page.goto("/matches");
    await expect(page.getByText(/^\d+ \/ \d+$/)).toBeVisible();
    await expect(page.locator(".sweep")).toBeHidden();
    await expect(page.getByText(/^Scan complete! \d+ projects? checked\./)).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".silhouette")).toHaveCount(0);
  });

  test("hover and press don't lift, tilt or push anything", async ({ page }) => {
    await scanDone(page);
    const transform = (target: ReturnType<Page["locator"]>) => target.evaluate((el) => getComputedStyle(el).transform);
    const card = page.locator("article.dex-card").first();
    await card.hover();
    expect(await transform(card)).toBe("none");
    const star = card.locator(".star svg");
    await star.hover();
    expect(await transform(star)).toBe("none");
    const rerun = page.getByRole("button", { name: "Run the scan again" });
    await rerun.hover();
    expect(await transform(rerun)).toBe("none");
    await page.mouse.down();
    expect(await transform(rerun)).toBe("none");
    await page.mouse.move(0, 0);
    await page.mouse.up();
  });

  test("with motion allowed, the same check does see the morph", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await scanDone(page);
    await page.locator("article h2 button").first().click();
    // Animation is the Web Animations API (the FLIP morph); CSS ones report as CSSAnimation.
    expect(await liveAnimations(page)).toContain("Animation");
  });
});
