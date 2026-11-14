import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { DECK, foundOf, stubApi } from "../test/api";
import { haveCount } from "./haveCount";

beforeEach(() => {
  useDevice.setState({
    ...emptyDevice,
    foodRulesSeen: true,
    pantry: ["paneer"],
    hydration: "ready",
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("have counts the pantry and the staples you're not out of", () => {
  expect(
    haveCount(
      ["paneer", "salt", "onion", "cream"],
      new Set(["paneer"]),
      new Set(["salt", "onion"]),
      new Set(["onion"]),
    ),
  ).toBe(2);
});

test("typing in the pantry's box lists matching recipes, and See all opens the rest", async () => {
  stubApi();
  window.history.pushState({}, "", "/");
  const user = userEvent.setup();
  render(<App />);
  const box = await screen.findByRole("searchbox", {
    name: "Search recipes or ingredients",
  });

  await user.type(box, "a");
  // One letter searches ingredients only.
  expect(screen.queryByRole("region", { name: "Recipes" })).not.toBeInTheDocument();

  await user.type(box, "l");
  const results = await screen.findByRole("region", { name: "Recipes" });
  const row = await within(results).findByRole("link", { name: /Aloo Gobi/ });
  expect(row).toHaveAttribute("href", `/recipe/${DECK[1]?.id ?? ""}`);
  // Aloo gobi needs potato, cauliflower, cream and salt; salt is a staple.
  expect(row).toHaveTextContent("North Indian · 30 min · have 1 of 4");
});

test("See all shows every match and pages through them", async () => {
  const many = Array.from({ length: 25 }, (_, n) => ({
    ...foundOf(DECK[0] as (typeof DECK)[0]),
    id: `00000000-0000-4000-8000-1000000000${String(n).padStart(2, "0")}`,
    name: `Paneer dish ${String(n + 1)}`,
  }));
  stubApi();
  const fetch = globalThis.fetch;
  vi.stubGlobal("fetch", async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname !== "/api/v1/recipes") return fetch(request);
    const offset = Number(url.searchParams.get("offset"));
    const limit = Number(url.searchParams.get("limit"));
    return Response.json({ results: many.slice(offset, offset + limit), total: 25 });
  });
  window.history.pushState({}, "", "/search?q=paneer");
  const user = userEvent.setup();
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "25 recipes" }, { timeout: 5000 }),
  ).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getAllByRole("link", { name: /Paneer dish/ })).toHaveLength(20);
  });
  await user.click(screen.getByRole("button", { name: "Show more" }));
  await waitFor(() => {
    expect(screen.getAllByRole("link", { name: /Paneer dish/ })).toHaveLength(25);
  });
  expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  // Paneer is in the pantry, so its ingredient chip is ticked.
  expect(
    screen.getByRole("button", { name: /Paneer/, pressed: true }),
  ).toBeInTheDocument();
});

test("paging stops at the API's deepest page and says why", async () => {
  const row = (n: number) => ({
    ...foundOf(DECK[0] as (typeof DECK)[0]),
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    name: `Curry ${String(n + 1)}`,
  });
  stubApi();
  const fetch = globalThis.fetch;
  vi.stubGlobal("fetch", async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname !== "/api/v1/recipes") return fetch(request);
    const offset = Number(url.searchParams.get("offset"));
    const limit = Number(url.searchParams.get("limit"));
    if (offset > 200) return new Response(null, { status: 422 });
    const results = Array.from({ length: limit }, (_, n) => row(offset + n));
    return Response.json({ results, total: 554 });
  });
  window.history.pushState({}, "", "/search?q=curry");
  const user = userEvent.setup();
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "554 recipes" }, { timeout: 5000 }),
  ).toBeInTheDocument();
  for (let shown = 20; shown < 220; shown += 20) {
    await waitFor(() => {
      expect(screen.getAllByRole("link", { name: /^Curry / })).toHaveLength(shown);
    });
    await user.click(screen.getByRole("button", { name: "Show more" }));
  }
  await waitFor(() => {
    expect(screen.getAllByRole("link", { name: /^Curry / })).toHaveLength(220);
  });
  expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  expect(
    screen.getByText("Showing the first 220. Add a word to narrow it down."),
  ).toBeInTheDocument();
}, 30_000);

test("the whole list ends without the narrowing hint", async () => {
  stubApi();
  window.history.pushState({}, "", "/search?q=aloo");
  render(<App />);
  expect(
    await screen.findByRole("heading", { name: /^\d+ recipes?$/ }, { timeout: 5000 }),
  ).toBeInTheDocument();
  expect(screen.queryByText(/Showing the first/)).not.toBeInTheDocument();
});

test("a result that breaks the food rules says so in red, and still shows", async () => {
  useDevice.setState({ avoidAllergens: ["dairy"], diet: "vegan" });
  stubApi();
  const fetch = globalThis.fetch;
  vi.stubGlobal("fetch", async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname !== "/api/v1/recipes") return fetch(request);
    return Response.json({
      results: [{ ...foundOf(DECK[0] as (typeof DECK)[0]), allergens: ["dairy"] }],
      total: 1,
    });
  });
  window.history.pushState({}, "", "/search?q=matar");
  render(<App />);

  const row = await screen.findByRole(
    "link",
    { name: /Matar Paneer/ },
    { timeout: 5000 },
  );
  expect(row).toHaveTextContent("Contains dairy");
  expect(row).toHaveTextContent("Not for your diet");
});

test("the deck and the cookbook open search", async () => {
  stubApi();
  window.history.pushState({}, "", "/saved");
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("link", { name: "Search recipes" }));

  expect(
    await screen.findByRole("searchbox", { name: "Search recipes or ingredients" }),
  ).toHaveFocus();
  expect(screen.getByText(/Type a dish, an ingredient or a cuisine/)).toBeInTheDocument();
});

test("while the next search loads, the last answer still names its own text", async () => {
  stubApi();
  const fetch = globalThis.fetch;
  vi.stubGlobal("fetch", async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname !== "/api/v1/recipes") return fetch(request);
    // The second search never answers, so the first stays on screen.
    if (url.searchParams.get("q") !== "zz") return new Promise<Response>(() => {});
    return Response.json({ results: [], total: 0 });
  });
  window.history.pushState({}, "", "/search?q=zz");
  const user = userEvent.setup();
  render(<App />);

  expect(
    await screen.findByRole(
      "heading",
      { name: "No recipe matches “zz”" },
      { timeout: 5000 },
    ),
  ).toBeInTheDocument();
  await user.type(
    screen.getByRole("searchbox", { name: "Search recipes or ingredients" }),
    "q",
  );
  // Past the 200 ms pause, so the next search has started.
  await new Promise((resolve) => setTimeout(resolve, 400));
  expect(
    screen.getByRole("heading", { name: "No recipe matches “zz”" }),
  ).toBeInTheDocument();
});
