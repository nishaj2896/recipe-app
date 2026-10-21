import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

let dealtOnce = false;

afterEach(() => {
  vi.unstubAllGlobals();
  dealtOnce = false;
});

/** Opens the deck and skips the cooking scene once the cards are ready. */
async function openDeck(search?: SearchHandler) {
  const api = stubApi(search);
  const user = userEvent.setup();
  render(<App />);
  // A cold run transforms the lazy deck chunk here, which can pass 1 s.
  expect(
    await screen.findByText(/Cooking up ideas/, undefined, { timeout: 5000 }),
  ).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Skip" }));
  // Let the scene fade out, so a later search's scene is the only one.
  await waitFor(() => {
    expect(screen.queryByText(/Cooking up ideas/)).not.toBeInTheDocument();
  });
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
    diet: null,
    max_total_minutes: null,
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
  expect(
    screen.getByRole("link", { name: "Your cookbook: 1 saved" }),
  ).toBeInTheDocument();

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

test("browser shortcuts and held keys never skip a card", async () => {
  const { user } = await openDeck();

  await user.keyboard("{Alt>}{ArrowLeft}{/Alt}");
  await user.keyboard("{Meta>}{ArrowLeft}{/Meta}");
  // A held key's repeats.
  fireEvent.keyDown(window, { key: "ArrowLeft", repeat: true });
  // Long enough for a fling to land, had one started.
  await new Promise((resolve) => setTimeout(resolve, 1500));

  expect(topCard()).toHaveAccessibleName("Matar Paneer");
  expect(useDevice.getState().hidden).toEqual([]);
});

test("the info button opens the recipe, and saving there swipes the card", async () => {
  const { user } = await openDeck();

  await user.click(screen.getByRole("button", { name: "About Matar Paneer" }));
  const sheet = await screen.findByRole("dialog", { name: "About this recipe" });
  // The sheet's own title is the h2, so the recipe's name comes one level down.
  expect(
    await within(sheet).findByRole("heading", { level: 3, name: "Matar Paneer" }),
  ).toBeInTheDocument();
  expect(
    await within(sheet).findByRole("region", { name: "You have" }),
  ).toHaveTextContent("Paneer");

  await user.click(within(sheet).getByRole("button", { name: "Save" }));
  await nextCardIs("Aloo Gobi");
  expect(useDevice.getState().saved).toEqual([matar.id]);
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

test("Backspace undoes too, and a screen reader hears the deal, every swipe and undo", async () => {
  const { user } = await openDeck();
  const status = () =>
    screen
      .getAllByRole("status")
      .find((element) => element.textContent.match(/Your deck has|Saved|Skipped|Undid/));

  // The first card is spoken when the deal appears.
  expect(status()).toHaveTextContent(
    /^Your deck has 3 recipes\. First: Matar Paneer, 67% match, missing cream\.$/,
  );

  await user.keyboard("{ArrowRight}");
  await nextCardIs("Aloo Gobi");
  expect(status()).toHaveTextContent(
    /^Saved Matar Paneer\. Next: Aloo Gobi, \d+% match, missing cauliflower, cream\.$/,
  );

  await user.keyboard("{Backspace}");
  await nextCardIs("Matar Paneer");
  expect(useDevice.getState().saved).toEqual([]);
  expect(status()).toHaveTextContent("Undid the save of Matar Paneer. It's back on top.");

  // Nothing left to undo: Backspace does nothing.
  await user.keyboard("{Backspace}");
  expect(topCard()).toHaveAccessibleName("Matar Paneer");
});

test("the save, skip and undo buttons name their keys", async () => {
  await openDeck();

  expect(screen.getByRole("button", { name: "Save Matar Paneer" })).toHaveAttribute(
    "aria-keyshortcuts",
    "ArrowRight",
  );
  expect(screen.getByRole("button", { name: "Skip Matar Paneer" })).toHaveAttribute(
    "aria-keyshortcuts",
    "ArrowLeft",
  );
  expect(screen.getByRole("button", { name: "Undo last swipe" })).toHaveAttribute(
    "aria-keyshortcuts",
    "Backspace",
  );
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

test("a fresh deck after a stale cursor doesn't count earlier saves again", async () => {
  const { user } = await openDeck((body) => {
    if (body.cursor) {
      return Response.json(
        { type: "/problems/cursor-expired", title: "Cursor expired", status: 422 },
        { status: 422, headers: { "content-type": "application/problem+json" } },
      );
    }
    // The first deck is one card; the fresh one deals everything not hidden.
    const results = body.hidden_recipe_ids.length === 0 && !dealtOnce ? [matar] : DECK;
    dealtOnce = true;
    return { results, next_cursor: "page-2", ignored_ingredients: [] };
  });

  await user.click(screen.getByRole("button", { name: "Save Matar Paneer" }));
  await user.click(await screen.findByRole("button", { name: "Deal more" }));
  await user.click(await screen.findByRole("button", { name: "Deal a fresh deck" }));
  await user.click(await screen.findByRole("button", { name: "Skip" }));

  await nextCardIs("Aloo Gobi");
  expect(screen.getByText("Your deck · 1 of 2")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Skip Aloo Gobi" }));
  await nextCardIs("Egg Bhurji");
  await user.click(screen.getByRole("button", { name: "Skip Egg Bhurji" }));

  expect(
    await screen.findByText("Nothing caught your eye this time."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("list")).not.toBeInTheDocument();
});

test("pantry items the API now ignores are taken out, and the user is told", async () => {
  await openDeck((body) => ({
    results: DECK.filter((card) => !body.hidden_recipe_ids.includes(card.id)),
    next_cursor: null,
    ignored_ingredients: [
      { id: "milk", name: "Milk", reason: "retired" },
      // Sent as out of stock, never in the pantry: not announced.
      { id: "old-spice", name: "Old spice", reason: "retired" },
    ],
  }));

  expect(screen.getByText(/We took milk out of your pantry:/)).toHaveAttribute(
    "role",
    "status",
  );
  expect(useDevice.getState().pantry).toEqual(["paneer", "potato", "egg"]);
});

test("an empty pantry is sent back to fill it, without searching", async () => {
  useDevice.setState({ pantry: [] });
  const { searches } = stubApi();
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Your pantry is empty" }),
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

test("the first visit shows the swipe hint until the first swipe, then never again", async () => {
  const { user } = await openDeck();

  expect(within(topCard()).getByText("Swipe right to save, left to skip")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "Skip Matar Paneer" }));
  await nextCardIs("Aloo Gobi");
  expect(within(topCard()).queryByText(/Swipe right/)).not.toBeInTheDocument();
  expect(useDevice.getState().swipeHintSeen).toBe(true);
});

test("the hint isn't shown once the user has swiped before", async () => {
  useDevice.setState({ swipeHintSeen: true });
  await openDeck();

  expect(within(topCard()).queryByText(/Swipe right/)).not.toBeInTheDocument();
  // The quiet reminder under the deck stays.
  expect(screen.getByText("Swipe right to save, left to skip")).toBeInTheDocument();
});

test("the deck's filters are sent, and changing them deals a fresh deck", async () => {
  useDevice.setState({ diet: "vegetarian" });
  const { user, api } = await openDeck();
  expect(api.searches[0]).toMatchObject({ diet: "vegetarian", max_total_minutes: null });

  await user.click(screen.getByRole("button", { name: "Filters: Veg · Any time" }));
  const sheet = await screen.findByRole("dialog", { name: "Filters" });
  const apply = within(sheet).getByRole("button", { name: "Show recipes" });
  expect(apply).toBeDisabled();

  await user.click(within(sheet).getByRole("radio", { name: "Vegan" }));
  await user.click(within(sheet).getByRole("radio", { name: "≤30 min" }));
  await user.click(apply);

  expect(screen.getByText(/Cooking up ideas/)).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Skip" }));
  await nextCardIs("Matar Paneer");
  expect(api.searches[1]).toMatchObject({
    diet: "vegan",
    max_total_minutes: 30,
    cursor: null,
  });
  expect(useDevice.getState()).toMatchObject({ diet: "vegan", maxTotalMinutes: 30 });
  expect(
    screen.getByRole("button", { name: "Filters: Vegan · ≤30 min" }),
  ).toBeInTheDocument();
});

test("closing the filters without applying keeps the deck", async () => {
  const { user, api } = await openDeck();

  await user.click(screen.getByRole("button", { name: /^Filters:/ }));
  const sheet = await screen.findByRole("dialog", { name: "Filters" });
  await user.click(within(sheet).getByRole("radio", { name: "Vegan" }));
  await user.click(within(sheet).getByRole("button", { name: "Done" }));

  expect(topCard()).toHaveAccessibleName("Matar Paneer");
  expect(api.searches).toHaveLength(1);
  expect(useDevice.getState().diet).toBeNull();
});

test("when filters leave nothing to cook, they can be cleared", async () => {
  useDevice.setState({ maxTotalMinutes: 15 });
  const { user, api } = await openDeck((body) => ({
    results: body.max_total_minutes === null ? DECK : [],
    next_cursor: null,
    ignored_ingredients: [],
  }));

  expect(
    screen.getByText("No recipe matches this pantry with these filters."),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Clear filters" }));
  await user.click(await screen.findByRole("button", { name: "Skip" }));

  await nextCardIs("Matar Paneer");
  expect(api.searches[1]).toMatchObject({ max_total_minutes: null });
  expect(useDevice.getState().maxTotalMinutes).toBeNull();
});

test("a save is kept even if the user leaves before the card has flown off", async () => {
  const { user } = await openDeck();

  await user.click(screen.getByRole("button", { name: "Save Matar Paneer" }));
  // Straight away, mid-flight: the card is still on top.
  expect(topCard()).toHaveAccessibleName("Matar Paneer");
  expect(screen.getByRole("button", { name: "Undo last swipe" })).toBeDisabled();
  await user.click(screen.getByRole("link", { name: "Your cookbook: 1 saved" }));

  expect(useDevice.getState().saved).toEqual([matar.id]);
  expect(
    await screen.findByRole("heading", { name: "Your cookbook" }),
  ).toBeInTheDocument();
});
