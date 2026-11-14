import { expect, test, type Response } from "@playwright/test";

import { fillPantry, openMood } from "./app";

interface Card {
  diet: string;
  jain: boolean;
  allergens: string[];
  courses: string[];
  total_minutes: number;
}

const isSearch = (response: Response) =>
  response.url().endsWith("/api/v1/recipes/search") && response.ok();

test("food rules and mood picks reach the API, deal only matching recipes and are remembered", async ({
  page,
}) => {
  await fillPantry(page);
  await page.getByRole("link", { name: "Your food rules" }).click();
  await page.getByRole("radio", { name: /^Vegetarian No meat/ }).check();
  await page.getByRole("button", { name: "Tree nuts" }).click();
  await page.getByRole("button", { name: "Save · avoiding 1" }).click();

  await openMood(page);
  await page.getByRole("button", { name: "Mains" }).click();
  await page.getByRole("radio", { name: "1 hr", exact: true }).check();
  const [response] = await Promise.all([
    page.waitForResponse(isSearch),
    page.getByRole("button", { name: "Deal my cards · 2 picked" }).click(),
  ]);

  const request = response.request().postDataJSON() as Record<string, unknown>;
  expect(request).toMatchObject({
    diet: "vegetarian",
    avoid_allergens: ["tree-nuts"],
    courses: ["mains"],
    max_total_minutes: 60,
  });
  const { results } = (await response.json()) as { results: Card[] };
  expect(results.length).toBeGreaterThan(0);
  for (const card of results) {
    expect(["vegan", "vegetarian"]).toContain(card.diet);
    expect(card.allergens).not.toContain("tree-nuts");
    expect(card.courses).toContain("mains");
    expect(card.total_minutes).toBeLessThanOrEqual(60);
  }
  await expect(
    page.getByRole("link", { name: "Your food rules: Veg · No tree nuts" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Your picks: Mains · 1 hr" }),
  ).toBeVisible();

  // The next deck, after a reload, starts with the same rules and picks.
  const [again] = await Promise.all([page.waitForResponse(isSearch), page.reload()]);
  expect(again.request().postDataJSON()).toMatchObject({
    diet: "vegetarian",
    avoid_allergens: ["tree-nuts"],
    courses: ["mains"],
    max_total_minutes: 60,
  });
});

test("Jain deals only Jain recipes", async ({ page }) => {
  await fillPantry(page);
  await page.getByRole("link", { name: "Your food rules" }).click();
  await page.getByRole("radio", { name: /^Jain/ }).check();
  await page.getByRole("button", { name: "Save" }).click();

  await openMood(page);
  const [response] = await Promise.all([
    page.waitForResponse(isSearch),
    page.getByRole("button", { name: "Deal my cards" }).click(),
  ]);

  expect(response.request().postDataJSON()).toMatchObject({
    diet: "vegetarian",
    jain: true,
  });
  const { results } = (await response.json()) as { results: Card[] };
  for (const card of results) expect(card.jain).toBe(true);
});
