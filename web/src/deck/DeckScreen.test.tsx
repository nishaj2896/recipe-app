import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { DECK, recipe, type SearchHandler, stubApi } from "../test/api";

const [matar, aloo, bhurji] = DECK as [
  (typeof DECK)[0],
  (typeof DECK)[0],
  (typeof DECK)[0],
];

beforeEach(() => {
  useDevice.setState({
    ...emptyDevice,
    pantry: ["paneer", "potato", "egg", "milk"],
    hydration: "ready",
  });
  window.history.pushState({}, "", "/deck");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Opens the deck and skips the cooking scene once the cards are ready. */
async function openDeck(search?: SearchHandler) {
  const api = stubApi(search);
  const user = userEvent.setup();
  render(<App />);
  expect(screen.getByText(/Cooking up ideas/)).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Skip" }));
  return { user, api };
}

const topCard = () => screen.getByRole("article");

async function nextCardIs(name: string) {
  await waitFor(
    () => {
      expect(topCard()).toHaveAccessibleName(name);
    },
    { timeout: 3000 },
  );
}

test("the search sends the pantry, the staples you're out of, and what you've skipped", async () => {
  useDevice.setState({ outOfStaples: ["salt"], hidden: ["an-old-skip"] });
  const { api } = await openDeck();

  expect(api.searches[0]).toEqual({
    limit: 20,
    ingredient_ids: ["paneer", "potato", "egg", "milk"],
    excluded_staples: ["salt"],
    hidden_recipe_ids: ["an-old-skip"],
    cursor: null,
  });
});

test("a card shows the match, what you have, and the one thing you're missing", async () => {
  await openDeck();
  const card = topCard();

  expect(card).toHaveAccessibleName("Matar Paneer");
  expect(within(card).getByRole("img", { name: "67% match" })).toBeInTheDocument();
  expect(card).toHaveTextContent("You have paneer, potato + staples");
  expect(card).toHaveTextContent("Add cream → 100% match");
  expect(card).toHaveTextContent("30 min");
  expect(screen.getByText("Your deck · 1 of 3")).toBeInTheDocument();
});

test("save and skip buttons swipe the card and remember the choice", async () => {
  const { user } = await openDeck();

  await user.click(screen.getByRole("button", { name: "Save Matar Paneer" }));
  await nextCardIs("Aloo Gobi");
  expect(useDevice.getState().saved).toEqual([matar.id]);
  expect(screen.getByRole("img", { name: "1 saved" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Skip Aloo Gobi" }));
  await nextCardIs("Egg Bhurji");
  expect(useDevice.getState().hidden).toEqual([aloo.id]);
});

test("the arrow keys swipe too", async () => {
  const { user } = await openDeck();

  await user.keyboard("{ArrowLeft}");
  await nextCardIs("Aloo Gobi");
  await user.keyboard("{ArrowRight}");
  await nextCardIs("Egg Bhurji");

  expect(useDevice.getState()).toMatchObject({ hidden: [matar.id], saved: [aloo.id] });
});

test("undo brings the last card back and forgets the choice", async () => {
  const { user } = await openDeck();
  const undo = screen.getByRole("button", { name: "Undo last swipe" });
  expect(undo).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Save Matar Paneer" }));
  await nextCardIs("Aloo Gobi");
  await user.click(undo);

  await nextCardIs("Matar Paneer");
  expect(useDevice.getState().saved).toEqual([]);
});

test("recipes saved earlier aren't dealt again", async () => {
  useDevice.setState({ saved: [aloo.id] });
  const { user } = await openDeck();

  await user.click(screen.getByRole("button", { name: "Skip Matar Paneer" }));
  await nextCardIs("Egg Bhurji");
  expect(screen.getByText("Your deck · 2 of 2")).toBeInTheDocument();
});

test("the end of the deck sums up the saves and lists what to buy", async () => {
  const { user } = await openDeck();

  await user.click(screen.getByRole("button", { name: "Save Matar Paneer" }));
  await nextCardIs("Aloo Gobi");
  await user.click(screen.getByRole("button", { name: "Save Aloo Gobi" }));
  await nextCardIs("Egg Bhurji");
  await user.click(screen.getByRole("button", { name: "Skip Egg Bhurji" }));

  expect(
    await screen.findByRole("heading", { name: "That's every match" }),
  ).toBeInTheDocument();
  expect(screen.getByText("You saved 2 recipes.")).toBeInTheDocument();
  const items = within(screen.getByRole("list")).getAllByRole("listitem");
  expect(items.map((item) => item.textContent)).toEqual([
    "Cream2 recipes",
    "Cauliflower1 recipe",
  ]);
  expect(useDevice.getState().hidden).toEqual([bhurji.id]);
});

test("deal more fetches the next deck with the cursor and the new skips", async () => {
  const second = recipe(4, "Palak Paneer", ["paneer"], ["spinach"]);
  const { user, api } = await openDeck((body) =>
    body.cursor
      ? { results: [second], next_cursor: null, ignored_ingredients: [] }
      : { results: [matar], next_cursor: "page-2", ignored_ingredients: [] },
  );

  await user.click(screen.getByRole("button", { name: "Skip Matar Paneer" }));
  await user.click(await screen.findByRole("button", { name: "Deal more" }));
  expect(screen.getByText(/Cooking up ideas/)).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Skip" }));

  await nextCardIs("Palak Paneer");
  expect(api.searches[1]).toMatchObject({
    cursor: "page-2",
    hidden_recipe_ids: [matar.id],
  });
});

test("pantry items the API now ignores are taken out, and the user is told", async () => {
  await openDeck((body) => ({
    results: DECK.filter((card) => !body.hidden_recipe_ids.includes(card.id)),
    next_cursor: null,
    ignored_ingredients: [{ id: "milk", name: "Milk", reason: "retired" }],
  }));

  expect(screen.getByText(/We took milk out of your pantry/)).toHaveAttribute(
    "role",
    "status",
  );
  expect(useDevice.getState().pantry).toEqual(["paneer", "potato", "egg"]);
});

test("an empty pantry is sent back to fill it, without searching", () => {
  useDevice.setState({ pantry: [] });
  const { searches } = stubApi();
  render(<App />);

  expect(
    screen.getByRole("heading", { name: "Your pantry is empty" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Fill your pantry" })).toHaveAttribute(
    "href",
    "/",
  );
  expect(searches).toEqual([]);
});

test("a failed search can be retried", async () => {
  let calls = 0;
  stubApi(() => {
    calls += 1;
    return calls === 1
      ? new Response(JSON.stringify({ title: "Boom", status: 500 }), {
          status: 500,
          headers: { "content-type": "application/problem+json" },
        })
      : { results: DECK, next_cursor: null, ignored_ingredients: [] };
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Try again" }));
  await user.click(await screen.findByRole("button", { name: "Skip" }));
  await nextCardIs("Matar Paneer");
});
