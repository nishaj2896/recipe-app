import { expect, test } from "@playwright/test";

import { openPantry, PHONE } from "./app";

test.use(PHONE);

// ADR-0012 rules 10 and 11: one box finds recipes and ingredients.
test("the pantry box finds recipes, and See all lists every match", async ({ page }) => {
  await openPantry(page);
  await page
    .getByRole("searchbox", { name: "Search recipes or ingredients" })
    .fill("paneer");

  const recipes = page.getByRole("region", { name: "Recipes" });
  await expect(recipes.getByRole("link").first()).toBeVisible();
  // The ingredient tile stays, so the same box still fills the pantry.
  await expect(page.getByRole("button", { name: "Paneer", exact: true })).toBeVisible();

  await recipes.getByRole("link", { name: /^See all \d+ recipes$/ }).click();
  await expect(page).toHaveURL(/\/search\?q=paneer$/);
  await expect(
    page.getByRole("heading", { level: 2, name: /^\d+ recipes$/ }),
  ).toBeVisible();

  // The ingredient chip adds paneer to the pantry from here too.
  await page.getByRole("button", { name: /Paneer$/, pressed: false }).click();
  await expect(
    page.getByRole("button", { name: /Paneer$/, pressed: true }),
  ).toBeVisible();

  await page.getByRole("main").getByRole("list").getByRole("link").first().click();
  await expect(page).toHaveURL(/\/recipe\//);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("search opens from the cookbook and finds by cuisine", async ({ page }) => {
  await openPantry(page);
  await page.goto("/saved");
  await page.getByRole("link", { name: "Search recipes" }).click();
  await page
    .getByRole("searchbox", { name: "Search recipes or ingredients" })
    .fill("thai");
  await expect(
    page.getByRole("heading", { level: 2, name: /^\d+ recipes?$/ }),
  ).toBeVisible();
  await page
    .getByRole("searchbox", { name: "Search recipes or ingredients" })
    .fill("zzqx");
  await expect(
    page.getByRole("heading", { level: 2, name: "No recipe matches “zzqx”" }),
  ).toBeVisible();
});
