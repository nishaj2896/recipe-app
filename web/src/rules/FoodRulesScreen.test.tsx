import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { stubApi } from "../test/api";

beforeEach(() => {
  stubApi();
  useDevice.setState({ ...emptyDevice, hydration: "ready" });
  window.history.pushState({}, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openFirstVisit() {
  const user = userEvent.setup();
  render(<App />);
  // The pantry sends a first visit to the food rules.
  expect(
    await screen.findByRole("heading", { name: "Your food rules" }, { timeout: 5000 }),
  ).toBeInTheDocument();
  return user;
}

test("a first visit opens the food rules once; skipping keeps them empty", async () => {
  const user = await openFirstVisit();
  expect(screen.getByText("Set up once")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Skip for now" }));

  expect(
    await screen.findByRole("searchbox", { name: "Search recipes or ingredients" }),
  ).toBeInTheDocument();
  expect(useDevice.getState()).toMatchObject({
    foodRulesSeen: true,
    diet: null,
    jain: false,
    avoidAllergens: [],
  });
});

test("Jain saves a veg diet with the Jain flag, and allergies are counted", async () => {
  const user = await openFirstVisit();

  await user.click(screen.getByRole("radio", { name: /^Jain/ }));
  await user.click(screen.getByRole("button", { name: "Peanuts" }));
  await user.click(screen.getByRole("button", { name: "Tree nuts" }));
  expect(screen.getByRole("button", { name: "Tree nuts" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await user.click(screen.getByRole("button", { name: "Save · avoiding 2" }));

  expect(useDevice.getState()).toMatchObject({
    foodRulesSeen: true,
    diet: "vegetarian",
    jain: true,
    avoidAllergens: ["peanuts", "tree-nuts"],
  });
  expect(
    await screen.findByRole("searchbox", { name: "Search recipes or ingredients" }),
  ).toBeInTheDocument();
});

test("gluten brings the note about hing", async () => {
  const user = await openFirstVisit();
  expect(screen.queryByText(/Hing \(asafoetida\)/)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Gluten" }));

  expect(screen.getByText(/Hing \(asafoetida\) isn't counted as gluten/)).toBeVisible();
});

test("any ingredient can be avoided, staples included, and taken off again", async () => {
  const user = await openFirstVisit();

  await user.click(
    screen.getByRole("button", { name: "+ Something else? Search any ingredient" }),
  );
  const search = screen.getByRole("searchbox", { name: "Search an ingredient to avoid" });
  expect(search).toHaveFocus();
  await user.type(search, "sal");
  await user.click(screen.getByRole("button", { name: "Avoid Salt" }));
  await user.type(search, "brinj");
  await user.click(screen.getByRole("button", { name: "Avoid Brinjal" }));

  const avoided = screen.getByRole("group", { name: "Ingredients you avoid" });
  await user.click(within(avoided).getByRole("button", { name: "Stop avoiding Salt" }));
  await user.click(screen.getByRole("button", { name: "Save · avoiding 1" }));

  expect(useDevice.getState().avoidIngredients).toEqual(["brinjal"]);
});

test("from the profile, the saved rules show and Back keeps them as they were", async () => {
  useDevice.setState({
    foodRulesSeen: true,
    diet: "vegan",
    avoidAllergens: ["soy"],
    avoidIngredients: ["paneer"],
  });
  window.history.pushState({}, "", "/food-rules");
  const user = userEvent.setup();
  render(<App />);

  expect(await screen.findByRole("radio", { name: /^Vegan/ })).toBeChecked();
  expect(screen.getByRole("button", { name: "Soy" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(
    await screen.findByRole("button", { name: "Stop avoiding Paneer" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Skip for now" })).not.toBeInTheDocument();

  await user.click(screen.getByRole("radio", { name: /^Anything/ }));
  await user.click(screen.getByRole("button", { name: "Back without saving" }));

  expect(useDevice.getState().diet).toBe("vegan");
  expect(
    await screen.findByRole("searchbox", { name: "Search recipes or ingredients" }),
  ).toBeInTheDocument();
});
