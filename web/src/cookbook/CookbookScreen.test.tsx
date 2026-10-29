import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { DECK, stubApi } from "../test/api";

const [matar, aloo] = DECK as [(typeof DECK)[0], (typeof DECK)[0]];
const GONE = "00000000-0000-4000-8000-00000000dead";

beforeEach(() => {
  stubApi();
  useDevice.setState({ ...emptyDevice, pantry: ["paneer"], hydration: "ready" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function open(path: string) {
  window.history.pushState({}, "", path);
  render(<App />);
  return userEvent.setup();
}

test("an empty cookbook points to the deck", async () => {
  open("/saved");

  expect(
    await screen.findByText("Recipes you swipe right on land here."),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Find something to cook" })).toHaveAttribute(
    "href",
    "/deck",
  );
});

test("saved recipes are listed newest first, and a missing one is kept as unavailable", async () => {
  useDevice.setState({ saved: [matar.id, GONE, aloo.id] });
  open("/saved");

  await screen.findByText("Unavailable right now");
  await screen.findByText("Matar Paneer");
  const rows = screen.getAllByRole("listitem");
  expect(rows.map((row) => row.textContent)).toEqual([
    "Aloo Gobi30 min · Vegetarian›×",
    "Unavailable right now›×",
    "Matar Paneer30 min · Vegetarian›×",
  ]);
  expect(useDevice.getState().saved).toEqual([matar.id, GONE, aloo.id]);
});

test("a recipe can be removed from the cookbook, and the removal undone", async () => {
  useDevice.setState({ saved: [matar.id, aloo.id] });
  const user = open("/saved");

  await user.click(
    await screen.findByRole("button", { name: "Remove Matar Paneer from your cookbook" }),
  );
  expect(useDevice.getState().saved).toEqual([aloo.id]);
  expect(screen.getByRole("status")).toHaveTextContent("Removed Matar Paneer.");
  // The removed row took the focused button with it: focus moves to Undo.
  expect(screen.getByRole("button", { name: "Undo" })).toHaveFocus();

  await user.click(screen.getByRole("button", { name: "Undo" }));
  // Back in its old place, not moved to newest.
  expect(useDevice.getState().saved).toEqual([matar.id, aloo.id]);
  expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(
    "Put Matar Paneer back in your cookbook.",
  );
  await waitFor(() => {
    expect(screen.getByRole("link", { name: /^Matar Paneer/ })).toHaveFocus();
  });
});

test("Remove all empties the cookbook, and Undo brings every recipe back", async () => {
  useDevice.setState({ saved: [matar.id, aloo.id] });
  const user = open("/saved");

  await user.click(await screen.findByRole("button", { name: "Remove all" }));
  expect(useDevice.getState().saved).toEqual([]);
  expect(screen.getByRole("status")).toHaveTextContent("Removed 2 recipes.");
  expect(screen.getByText("Recipes you swipe right on land here.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo" })).toHaveFocus();

  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(useDevice.getState().saved).toEqual([matar.id, aloo.id]);
  expect(await screen.findByText("Matar Paneer")).toBeInTheDocument();
  // Focus lands on the newest recipe, the top row.
  await waitFor(() => {
    expect(screen.getByRole("link", { name: /^Aloo Gobi/ })).toHaveFocus();
  });
});

test("a recipe sorts its ingredients into have, need and assumed staples", async () => {
  useDevice.setState({ saved: [matar.id], pantry: ["paneer"] });
  open(`/recipe/${matar.id}`);

  expect(
    await screen.findByRole("heading", { level: 1, name: "Matar Paneer" }),
  ).toBeInTheDocument();
  const items = (group: string) =>
    within(screen.getByRole("region", { name: group }))
      .getAllByRole("listitem")
      .map((item) => item.textContent);
  expect(items("You have")).toEqual(["Paneer1 cup"]);
  expect(items("You'll need")).toEqual(["Potato1 cup", "Cream1 cup"]);
  expect(items("Staples we assume you have")).toEqual(["Salt1 cup"]);
});

test("staples are never shown as needed while they're still loading", async () => {
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const fetch = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (new URL(request.url).pathname === "/api/v1/staples") await gate;
      return fetch(request);
    }),
  );
  open(`/recipe/${matar.id}`);

  // The recipe arrives first; it waits for the staples rather than guess.
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(screen.getByText("Loading the recipe…")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "You'll need" })).toBeNull();

  release();
  const assumed = await screen.findByRole("region", {
    name: "Staples we assume you have",
  });
  expect(within(assumed).getByText("Salt")).toBeInTheDocument();
});

test("a staple you're out of moves to what you'll need", async () => {
  useDevice.setState({ outOfStaples: ["salt"] });
  open(`/recipe/${matar.id}`);

  const need = await screen.findByRole("region", { name: "You'll need" });
  expect(within(need).getByText("Salt")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Staples we assume you have" })).toBeNull();
});

test("the save button saves and unsaves", async () => {
  useDevice.setState({ saved: [matar.id] });
  const user = open(`/recipe/${matar.id}`);

  const button = await screen.findByRole("button", { name: "♥ Saved" });
  await user.click(button);
  expect(useDevice.getState().saved).toEqual([]);
  expect(button).toHaveAttribute("aria-pressed", "false");

  await user.click(button);
  expect(useDevice.getState().saved).toEqual([matar.id]);
});

test("a recipe the API can't find right now says so", async () => {
  open(`/recipe/${GONE}`);

  expect(
    await screen.findByText(/This recipe isn't available right now/),
  ).toBeInTheDocument();
});

test("the pantry links to the cookbook once something is saved", async () => {
  const user = open("/");
  expect(screen.queryByRole("link", { name: /Your cookbook/ })).toBeNull();

  useDevice.getState().saveRecipe(matar.id);
  await user.click(await screen.findByRole("link", { name: "Your cookbook: 1 saved" }));

  expect(
    await screen.findByRole("heading", { name: "Your cookbook" }),
  ).toBeInTheDocument();
});
