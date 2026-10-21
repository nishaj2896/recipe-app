import { type Browser, expect, type Page, test } from "@playwright/test";

import { dragCard, fillPantry, openDeck, PHONE } from "./app";

// ADR-0006 rule 10: the app's three big motions, replayed on a CPU slowed
// 4×, must not block the main thread for long. The browser reports any task
// over 50 ms as a "longtask"; one that long drops frames, so the motion
// stutters on a mid-range phone.
const SLOWDOWN = 4;
// Timings on a shared CI machine are noisy, so each motion is replayed a few
// times in a fresh browser and judged by its best run. A real slowdown shows
// in every run; a hiccup from a busy machine doesn't.
const RUNS = 3;

declare global {
  interface Window {
    longTasks: number[];
  }
}

/**
 * Opens a fresh page, gets it ready with `setup`, then plays `motion` with
 * the CPU slowed and returns the longest task it caused, in ms (0 if none
 * was over 50 ms).
 */
async function longestTask(
  browser: Browser,
  baseURL: string,
  setup: (page: Page) => Promise<void>,
  motion: (page: Page) => Promise<void>,
): Promise<number> {
  const context = await browser.newContext({ ...PHONE, baseURL });
  try {
    const page = await context.newPage();
    await page.addInitScript(() => {
      window.longTasks = [];
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) window.longTasks.push(entry.duration);
      }).observe({ type: "longtask" });
    });
    await setup(page);
    const cdp = await context.newCDPSession(page);
    await page.evaluate(() => {
      window.longTasks = [];
    });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: SLOWDOWN });
    await motion(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    return await page.evaluate(() => Math.max(0, ...window.longTasks));
  } finally {
    await context.close();
  }
}

/** The best of a few runs of the same motion. */
async function bestOf(run: () => Promise<number>): Promise<number> {
  const runs: number[] = [];
  for (let index = 0; index < RUNS; index++) runs.push(await run());
  test
    .info()
    .annotations.push({ type: "longest tasks, ms", description: runs.join(", ") });
  return Math.min(...runs);
}

test("an ingredient flies into the jar without a long task", async ({
  browser,
  baseURL,
}) => {
  const longest = await bestOf(() =>
    longestTask(
      browser,
      baseURL ?? "",
      async (page) => {
        await fillPantry(page, ["Paneer"]);
        await page.getByRole("searchbox", { name: "Search ingredients" }).fill("Potato");
        await page.getByRole("button", { name: "Potato", exact: true }).hover();
      },
      async (page) => {
        await page.getByRole("button", { name: "Potato", exact: true }).click();
        await expect(
          page.getByRole("button", { name: "Your pantry: 2 ingredients" }),
        ).toBeVisible();
        await page.waitForTimeout(1500);
      },
    ),
  );
  expect(longest).toBe(0);
});

test("a swipe flies off without a long task", async ({ browser, baseURL }) => {
  const longest = await bestOf(() =>
    longestTask(
      browser,
      baseURL ?? "",
      async (page) => {
        await fillPantry(page);
        await openDeck(page);
        // The first swipe ends the first-run hint, so only a swipe is measured.
        await dragCard(page, 200);
        await expect(
          page.getByRole("link", { name: "Your cookbook: 1 saved" }),
        ).toBeVisible();
        await page.waitForTimeout(1000);
      },
      async (page) => {
        await dragCard(page, 200);
        await expect(
          page.getByRole("link", { name: "Your cookbook: 2 saved" }),
        ).toBeVisible();
        await page.waitForTimeout(1500);
      },
    ),
  );
  expect(longest).toBe(0);
});

// Dealing swaps the pantry screen for the deck, then draws the first card as
// the cooking scene fades. Each of those moments may take up to 100 ms
// (Nisha, 21 Oct): it happens once, behind the fade, not mid-motion.
const DEAL_BUDGET_MS = 100;

test("the deck deals within its budget", async ({ browser, baseURL }) => {
  const longest = await bestOf(() =>
    longestTask(
      browser,
      baseURL ?? "",
      async (page) => {
        await fillPantry(page);
        await page.getByRole("link", { name: /Cook something/ }).hover();
      },
      async (page) => {
        await page.getByRole("link", { name: /Cook something/ }).click();
        await expect(page.getByText("Cooking up ideas")).toHaveCount(0, {
          timeout: 15_000,
        });
        await expect(page.getByRole("article")).toBeVisible();
        await page.waitForTimeout(1000);
      },
    ),
  );
  expect(longest).toBeLessThanOrEqual(DEAL_BUDGET_MS);
});
