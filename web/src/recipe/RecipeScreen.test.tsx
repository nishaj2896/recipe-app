import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { DECK, detailOf, stubApi } from "../test/api";

const matar = DECK[0] as (typeof DECK)[0];

beforeEach(() => {
  useDevice.setState({ ...emptyDevice, pantry: ["paneer"], hydration: "ready" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function open() {
  window.history.pushState({}, "", `/recipe/${matar.id}`);
  render(<App />);
  return userEvent.setup();
}

/** Matar paneer as a file would write it: for 2, with one to-taste ingredient. */
function written(withPhoto: boolean) {
  stubApi(undefined, (card) => ({
    ...detailOf(card),
    serves: 2,
    ingredients: [
      { id: "paneer", name: "Paneer", amount: 200, unit: "g" },
      { id: "potato", name: "Potato", amount: 0.5, unit: "medium" },
      { id: "cream", name: "Cream", amount: 0.333, unit: "cup" },
      { id: "salt", name: "Salt", amount: null, unit: null },
    ],
    steps: ["Cube the paneer.", "Simmer everything with the cream."],
    image: withPhoto
      ? { url: `/dishes/${card.id}.webp?v=0123456789ab`, alt: "Matar paneer in a bowl" }
      : null,
  }));
}

function amounts() {
  return screen
    .getAllByRole("listitem")
    .filter((row) => row.closest("ol") === null)
    .map((row) => row.textContent);
}

test("the recipe shows its amounts, numbered method and photo", async () => {
  written(true);
  open();

  expect(
    await screen.findByRole("img", { name: "Matar paneer in a bowl" }),
  ).toHaveAttribute("src", `/dishes/${matar.id}.webp?v=0123456789ab`);
  expect(screen.getByRole("group", { name: "Servings" })).toHaveTextContent("2");
  expect(amounts()).toEqual([
    "Paneer200 g",
    "Potato½ medium",
    "Cream⅓ cup",
    "Saltto taste",
  ]);
  const method = within(screen.getByRole("region", { name: "Method" })).getByRole("list");
  expect(method.tagName).toBe("OL");
  expect(
    within(method)
      .getAllByRole("listitem")
      .map((step) => step.textContent),
  ).toEqual(["Cube the paneer.", "Simmer everything with the cream."]);
});

test("changing the servings scales every amount but to-taste ones", async () => {
  written(false);
  const user = open();

  await user.click(await screen.findByRole("button", { name: "More servings" }));
  await user.click(screen.getByRole("button", { name: "More servings" }));
  await user.click(screen.getByRole("button", { name: "More servings" }));

  expect(screen.getByRole("group", { name: "Servings" })).toHaveTextContent("5");
  expect(amounts()).toEqual([
    "Paneer500 g",
    "Potato1½ medium", // 1.25 is halfway, so up
    "Cream¾ cup", // 0.8325 is nearer ¾ than ⅔
    "Saltto taste",
  ]);
});

test("the servings stay between 1 and 12", async () => {
  written(false);
  const user = open();

  const fewer = await screen.findByRole("button", { name: "Fewer servings" });
  await user.click(fewer);
  expect(fewer).toBeDisabled();
  expect(amounts()[0]).toBe("Paneer100 g");

  const more = screen.getByRole("button", { name: "More servings" });
  for (let i = 0; i < 11; i += 1) await user.click(more);
  expect(more).toBeDisabled();
  expect(screen.getByRole("group", { name: "Servings" })).toHaveTextContent("12");
  expect(amounts()[0]).toBe("Paneer1.2 kg");
});

test("the drawn bowl stands in when the photo doesn't load", async () => {
  written(true);
  open();

  fireEvent.error(await screen.findByRole("img", { name: "Matar paneer in a bowl" }));

  expect(screen.queryByRole("img", { name: "Matar paneer in a bowl" })).toBeNull();
});

test("a recipe synced before amounts existed shows no stepper or amounts", async () => {
  stubApi(undefined, (card) => ({
    ...detailOf(card),
    serves: null,
    ingredients: detailOf(card).ingredients.map((item) => ({
      ...item,
      amount: null,
      unit: null,
    })),
    steps: [],
  }));
  open();

  await screen.findByRole("heading", { name: "Matar Paneer" });
  expect(screen.queryByRole("group", { name: "Servings" })).toBeNull();
  expect(screen.queryByRole("region", { name: "Method" })).toBeNull();
  expect(amounts()).toEqual(["Paneer", "Potato", "Cream", "Salt"]);
});
