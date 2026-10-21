import { expect, type Page } from "@playwright/test";

/** A mid-size phone: the app is designed mobile first. */
export const PHONE = { viewport: { width: 390, height: 844 }, hasTouch: true };

/** Ingredients that deal a full deck from the real catalog. */
export const PANTRY = ["Paneer", "Potato", "Peas", "Milk", "Egg", "Rice"];

/** Opens the pantry and adds each ingredient by searching for its tile. */
export async function fillPantry(page: Page, names: readonly string[] = PANTRY) {
  await page.goto("/");
  const search = page.getByRole("searchbox", { name: "Search ingredients" });
  for (const name of names) {
    await search.fill(name);
    await page.getByRole("button", { name, exact: true, pressed: false }).click();
  }
  await search.clear();
  await expect(
    page.getByRole("button", {
      name: `Your pantry: ${String(names.length)} ${names.length === 1 ? "ingredient" : "ingredients"}`,
    }),
  ).toBeVisible();
}

/** Goes from the pantry to the deck and waits for the first card. */
export async function openDeck(page: Page) {
  await page.getByRole("link", { name: /Cook something/ }).click();
  // The cooking scene fades out over the dealt card: wait until it's gone.
  await expect(page.getByText("Cooking up ideas")).toHaveCount(0);
  await expect(page.getByRole("article")).toBeVisible();
  return page.getByRole("article");
}

/** The recipe name on the top card. */
export async function topCardName(page: Page): Promise<string> {
  const name = await page.getByRole("article").getAttribute("aria-label");
  if (!name) throw new Error("the top card has no name");
  return name;
}

/**
 * Drags the top card sideways by `dx` pixels and lets go, the way a finger
 * would: a press, a run of small moves, a release.
 */
export async function dragCard(page: Page, dx: number) {
  const card = page.getByRole("article");
  // Hovering waits for the card to stop moving, so the press lands on it.
  await card.hover();
  const box = await card.boundingBox();
  if (!box) throw new Error("the card isn't on screen");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  for (let step = 1; step <= 10; step++) await page.mouse.move(x + (dx * step) / 10, y);
  await page.mouse.up();
}
