import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { stubApi } from "../test/api";

beforeEach(() => {
  stubApi();
  useDevice.setState({ ...emptyDevice, hydration: "ready" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openApp() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("button", { name: /Potato/ });
  return user;
}

test("the grid starts with popular ingredients the catalog has", async () => {
  await openApp();
  // Popular names ids the small test catalog lacks; only those it has show.
  const tiles = screen.getAllByRole("button", { pressed: false });
  expect(tiles.map((tile) => tile.textContent)).toEqual(
    expect.arrayContaining(["Potato", "Milk", "Paneer", "Egg", "Carrot"]),
  );
});

test("staples are never offered as tiles", async () => {
  const user = await openApp();
  await user.type(screen.getByRole("searchbox", { name: "Search ingredients" }), "salt");
  expect(screen.getByText(/No ingredient matches/)).toBeInTheDocument();
});

test("tapping a tile adds it to the pantry, flies it to the jar, and tapping again removes it", async () => {
  const user = await openApp();
  const milk = screen.getByRole("button", { name: /Milk/ });

  await user.click(milk);
  expect(milk).toHaveAttribute("aria-pressed", "true");
  expect(useDevice.getState().pantry).toEqual(["milk"]);
  expect(
    screen.getByRole("button", { name: "Your pantry: 1 ingredient" }),
  ).toBeInTheDocument();
  expect(screen.getByTestId("flight")).toBeInTheDocument();
  await waitFor(
    () => {
      expect(screen.queryByTestId("flight")).not.toBeInTheDocument();
    },
    { timeout: 4000 },
  );

  await user.click(milk);
  expect(milk).toHaveAttribute("aria-pressed", "false");
  expect(useDevice.getState().pantry).toEqual([]);
});

test("search finds an ingredient by another name", async () => {
  const user = await openApp();
  await user.type(
    screen.getByRole("searchbox", { name: "Search ingredients" }),
    "aubergine",
  );
  expect(screen.getByRole("button", { name: /Brinjal/ })).toBeInTheDocument();
});

test("a category tab shows that category's ingredients", async () => {
  const user = await openApp();
  await user.click(screen.getByRole("button", { name: "Vegetables" }));
  expect(screen.getByRole("button", { name: /Sweet potato/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Milk/ })).not.toBeInTheDocument();
});

test("a quick start adds the ingredients the catalog has", async () => {
  const user = await openApp();
  await user.click(screen.getByRole("button", { name: /Breakfast/ }));
  expect(useDevice.getState().pantry).toEqual(["egg", "milk", "potato"]);
});

test("the pantry sheet lists what's in the pantry and can remove it", async () => {
  useDevice.setState({ pantry: ["milk", "paneer", "an-id-this-catalog-lacks"] });
  const user = await openApp();

  await user.click(screen.getByRole("button", { name: "Your pantry: 2 ingredients" }));
  const sheet = screen.getByRole("dialog", { name: "Your pantry" });
  await user.click(within(sheet).getByRole("button", { name: "Remove Milk" }));

  // An id the catalog doesn't list is kept, never dropped (ADR-0006 rule 5).
  expect(useDevice.getState().pantry).toEqual(["paneer", "an-id-this-catalog-lacks"]);
});

test("staples are assumed, and the user can untick one they're out of", async () => {
  const user = await openApp();
  const strip = await screen.findByRole("region", { name: "Staples" });
  expect(strip).toHaveTextContent("Assuming you have onion, tomato, salt +1 staples");

  await user.click(within(strip).getByRole("button", { name: "Edit" }));
  const sheet = screen.getByRole("dialog", { name: "Staples you have" });
  await user.click(within(sheet).getByRole("checkbox", { name: "Salt" }));

  expect(useDevice.getState().outOfStaples).toEqual(["salt"]);
  expect(strip).toHaveTextContent("out of salt");
});

test("Cook something appears once the pantry has an ingredient", async () => {
  const user = await openApp();
  expect(screen.queryByRole("link", { name: /Cook something/ })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Egg/ }));
  expect(screen.getByRole("link", { name: /Cook something/ })).toHaveAttribute(
    "href",
    "/deck",
  );
});

test("with reduced motion on, nothing flies", async () => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
  const user = await openApp();

  await user.click(screen.getByRole("button", { name: /Milk/ }));
  expect(screen.queryByTestId("flight")).not.toBeInTheDocument();
  expect(useDevice.getState().pantry).toEqual(["milk"]);
});

test("a catalog that fails to load says so and offers a retry", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(null, { status: 503 }))),
  );
  render(<App />);
  expect(
    await screen.findByText(/couldn't load the ingredients/, {}, { timeout: 8000 }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
}, 10_000);

test("nothing can be tapped until the saved pantry has been read", async () => {
  useDevice.setState({ hydration: "pending" });
  render(<App />);
  expect(await screen.findByText("Loading ingredients…")).toBeInTheDocument();
  // Give the catalog time to arrive: the tiles still wait for the device data.
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(screen.queryByRole("button", { name: /Potato/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Breakfast/ })).not.toBeInTheDocument();

  act(() => {
    useDevice.setState({ hydration: "ready" });
  });
  expect(await screen.findByRole("button", { name: /Potato/ })).toBeInTheDocument();
});

test("when the saved pantry can't be read, the user is told it won't be saved", async () => {
  useDevice.setState({ hydration: "failed" });
  await openApp();
  expect(screen.getByRole("alert")).toHaveTextContent("won't be saved this visit");
});

test("the staples count ignores out-of-stock ids the staples list no longer has", async () => {
  useDevice.setState({ pantry: ["milk"], outOfStaples: ["salt", "a-retired-staple"] });
  await openApp();
  // Four staples in the list, one of them unticked.
  expect(await screen.findByText("+3 staples")).toBeInTheDocument();
});
