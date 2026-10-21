import { expect, test, type Response } from "@playwright/test";

import { fillPantry, openDeck } from "./app";

interface Card {
  diet: string;
  total_minutes: number;
}

const isSearch = (response: Response) =>
  response.url().endsWith("/api/v1/recipes/search") && response.ok();

test("filters reach the API, deal only matching recipes and are remembered", async ({
  page,
}) => {
  await fillPantry(page);
  await openDeck(page);

  await page.getByRole("button", { name: /^Filters:/ }).click();
  const sheet = page.getByRole("dialog", { name: "Filters" });
  await sheet.getByRole("radio", { name: "Vegetarian", exact: true }).check();
  await sheet.getByRole("radio", { name: "≤30 min" }).check();
  const [response] = await Promise.all([
    page.waitForResponse(isSearch),
    sheet.getByRole("button", { name: "Show recipes" }).click(),
  ]);

  const request = response.request().postDataJSON() as Record<string, unknown>;
  expect(request).toMatchObject({ diet: "vegetarian", max_total_minutes: 30 });
  const { results } = (await response.json()) as { results: Card[] };
  expect(results.length).toBeGreaterThan(0);
  for (const card of results) {
    expect(["vegan", "vegetarian"]).toContain(card.diet);
    expect(card.total_minutes).toBeLessThanOrEqual(30);
  }
  await expect(
    page.getByRole("button", { name: "Filters: Veg · ≤30 min" }),
  ).toBeVisible();

  // The next deck, after a reload, starts with the same filters.
  const [again] = await Promise.all([page.waitForResponse(isSearch), page.reload()]);
  expect(again.request().postDataJSON()).toMatchObject({
    diet: "vegetarian",
    max_total_minutes: 30,
  });
});
