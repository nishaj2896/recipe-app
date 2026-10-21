import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { fillPantry, openDeck, topCardName } from "./app";

// ADR-0006 rule 10: axe checks each screen and sheet against WCAG 2.2 AA.
async function expectAccessible(page: Page, screen: string) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const found = violations.map((violation) => ({
    screen,
    rule: violation.id,
    help: violation.help,
    nodes: violation.nodes.map(
      (node) => `${node.target.join(" ")}: ${node.failureSummary ?? ""}`,
    ),
  }));
  expect(found).toEqual([]);
}

for (const colorScheme of ["dark", "light"] as const) {
  test.describe(`${colorScheme} theme`, () => {
    // Reduced motion settles every screen at once, so nothing is checked mid-fade.
    test.use({ colorScheme, reducedMotion: "reduce" });

    test("empty screens", async ({ page }) => {
      await page.goto("/");
      await expect(
        page.getByRole("searchbox", { name: "Search ingredients" }),
      ).toBeVisible();
      await expectAccessible(page, "pantry, empty");

      await page.goto("/deck");
      await expect(
        page.getByRole("heading", { name: "Your pantry is empty" }),
      ).toBeVisible();
      await expectAccessible(page, "deck, empty pantry");

      await page.goto("/saved");
      await expect(page.getByRole("heading", { name: "Your cookbook" })).toBeVisible();
      await expectAccessible(page, "cookbook, empty");
    });

    test("pantry and its sheets", async ({ page }) => {
      await fillPantry(page);
      await expectAccessible(page, "pantry");

      await page.getByRole("button", { name: /^Your pantry:/ }).click();
      await expect(page.getByRole("dialog", { name: "Your pantry" })).toBeVisible();
      await expectAccessible(page, "pantry sheet");
      await page.getByRole("button", { name: "Done" }).click();

      await page
        .getByRole("region", { name: "Staples" })
        .getByRole("button", { name: "Edit" })
        .click();
      await expect(page.getByRole("dialog", { name: "Staples you have" })).toBeVisible();
      await expectAccessible(page, "staples sheet");
    });

    test("deck, its sheets, the recap and the cookbook", async ({ page }) => {
      await fillPantry(page);
      await openDeck(page);
      await expectAccessible(page, "deck");

      await page.getByRole("button", { name: /^Filters:/ }).click();
      await expect(page.getByRole("dialog", { name: "Filters" })).toBeVisible();
      await expectAccessible(page, "filters sheet");
      await page.getByRole("button", { name: "Done" }).click();

      const name = await topCardName(page);
      await page.getByRole("button", { name: `About ${name}`, exact: true }).click();
      await expect(page.getByRole("dialog").getByRole("heading", { name })).toBeVisible();
      await expectAccessible(page, "recipe sheet");
      await page.getByRole("button", { name: "Done" }).click();

      // Save every third card and skip the rest, to reach the recap.
      for (let swiped = 0; (await page.getByRole("article").count()) > 0; swiped++) {
        const current = await topCardName(page);
        const action = swiped % 3 === 0 ? "Save" : "Skip";
        await page
          .getByRole("button", { name: `${action} ${current}`, exact: true })
          .click();
        await expect(
          page.getByRole("article", { name: current, exact: true }),
        ).toHaveCount(0);
      }
      await expect(
        page.getByRole("heading", { name: "Shopping list from your saves" }),
      ).toBeVisible();
      await expectAccessible(page, "recap");

      await page.getByRole("link", { name: /Open your cookbook/ }).click();
      await expect(page.getByRole("heading", { name: "Your cookbook" })).toBeVisible();
      await expectAccessible(page, "cookbook");

      await page.getByRole("list").getByRole("link").first().click();
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expectAccessible(page, "recipe page");
    });
  });
}
