import { expect, test } from "@playwright/test";

import { fillPantry, openDeck } from "./app";

// Screens and animation features load as separate files (issue #52). These
// replay a dropped connection, or a deploy that renamed the files while the
// app was open, by refusing those requests.

test("a screen that can't load offers a reload, not a blank page", async ({ page }) => {
  await page.route(/\/assets\/CookbookScreen-[^/]*\.js$/, (route) => route.abort());
  await page.goto("/saved");

  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Couldn't load this screen");

  // Once the connection is back, Try again recovers.
  await page.unroute(/\/assets\/CookbookScreen-[^/]*\.js$/);
  await alert.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Your cookbook" })).toBeVisible();
});

test("without the animation code the app still deals and saves", async ({ page }) => {
  await page.route(/\/assets\/motionFeatures-[^/]*\.js$/, (route) => route.abort());
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));

  await fillPantry(page);
  // The cooking scene still gives way to the deck.
  await openDeck(page);
  const name = await page.getByRole("article").getAttribute("aria-label");
  await page.getByRole("button", { name: `Save ${name ?? ""}`, exact: true }).click();
  await expect(page.getByRole("link", { name: "Your cookbook: 1 saved" })).toBeVisible();

  expect(errors).toEqual([]);
});
