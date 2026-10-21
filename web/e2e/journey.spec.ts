import { expect, test } from "@playwright/test";

import { dragCard, fillPantry, openDeck, topCardName } from "./app";

test("pantry to deck to cookbook, and the saves survive a reload", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });

  await fillPantry(page);
  await openDeck(page);

  // Drag the first card right to save it.
  const saved = await topCardName(page);
  await dragCard(page, 200);
  await expect(page.getByRole("link", { name: "Your cookbook: 1 saved" })).toBeVisible();

  // Skip the next one with its button.
  await expect(page.getByRole("article")).not.toHaveAttribute("aria-label", saved);
  const skipped = await topCardName(page);
  await page.getByRole("button", { name: `Skip ${skipped}`, exact: true }).click();
  await expect(page.getByRole("article")).not.toHaveAttribute("aria-label", skipped);

  // A short drag springs back: it neither swipes nor counts as a tap.
  const third = await topCardName(page);
  await dragCard(page, 80);
  await expect(page.getByRole("dialog", { name: "About this recipe" })).toHaveCount(0);
  await expect(page.getByRole("article")).toHaveAttribute("aria-label", third);

  // Tap it to read about it, then save it from the sheet.
  await page.getByRole("article").click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: third })).toBeVisible();
  await sheet.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("link", { name: "Your cookbook: 2 saved" })).toBeVisible();

  // The cookbook lists both saves, newest first, and opens a recipe.
  await page.getByRole("link", { name: "Your cookbook: 2 saved" }).click();
  await expect(page.getByRole("heading", { name: "Your cookbook" })).toBeVisible();
  const rows = page.getByRole("list").getByRole("link");
  await expect(rows).toHaveCount(2);

  // A cold start reads everything back from the device.
  await page.reload();
  await expect(rows).toHaveCount(2);
  await rows.filter({ hasText: saved }).click();
  await expect(page.getByRole("heading", { name: saved, level: 1 })).toBeVisible();

  expect(errors).toEqual([]);
});
