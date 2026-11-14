import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { stubApi } from "../test/api";

beforeEach(() => {
  useDevice.setState({
    ...emptyDevice,
    foodRulesSeen: true,
    pantry: ["paneer"],
    hydration: "ready",
  });
  window.history.pushState({}, "", "/mood");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openMood() {
  const api = stubApi();
  const user = userEvent.setup();
  render(<App />);
  expect(
    await screen.findByRole(
      "heading",
      { name: "What are you making?" },
      { timeout: 5000 },
    ),
  ).toBeInTheDocument();
  return { user, api };
}

test("nothing picked deals today's deck", async () => {
  const { user, api } = await openMood();
  expect(
    screen.queryByRole("button", { name: "Show me everything" }),
  ).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Deal my cards" }));

  expect(await screen.findByText(/Cooking up ideas/)).toBeInTheDocument();
  expect(api.searches[0]).toMatchObject({
    courses: [],
    moods: [],
    weather: [],
    min_total_minutes: null,
    max_total_minutes: null,
  });
});

test("picks are counted, remembered and dealt", async () => {
  const { user, api } = await openMood();

  await user.click(screen.getByRole("button", { name: "Snacks and starters" }));
  await user.click(screen.getByRole("radio", { name: "1 hr+" }));
  // Mood and weather wait under Fine-tune.
  expect(screen.queryByRole("button", { name: "Spicy" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Fine-tune/ }));
  await user.click(screen.getByRole("button", { name: "Spicy" }));
  await user.click(screen.getByRole("button", { name: "Rainy-day cosy" }));
  expect(
    screen.getByRole("button", { name: /Fine-tune.*2 picked · Spicy, Rainy-day cosy/ }),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Deal my cards · 4 picked" }));

  expect(await screen.findByText(/Cooking up ideas/)).toBeInTheDocument();
  expect(useDevice.getState().mood).toEqual({
    courses: ["snacks-starters"],
    time: "over-60",
    moods: ["spicy"],
    weather: ["rainy-day-cosy"],
  });
  expect(api.searches[0]).toMatchObject({
    courses: ["snacks-starters"],
    min_total_minutes: 61,
    max_total_minutes: null,
    moods: ["spicy"],
    weather: ["rainy-day-cosy"],
  });
});

test("the last picks come back, and Show me everything clears them", async () => {
  useDevice.setState({
    mood: { courses: ["mains"], time: "30", moods: ["creamy"], weather: [] },
  });
  const { user, api } = await openMood();

  expect(screen.getByRole("button", { name: "Mains" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("radio", { name: "30 min" })).toBeChecked();
  // Fine-tune starts open when it holds a pick.
  expect(screen.getByRole("button", { name: "Creamy" })).toBeVisible();

  await user.click(screen.getByRole("button", { name: "Show me everything" }));

  expect(await screen.findByText(/Cooking up ideas/)).toBeInTheDocument();
  expect(useDevice.getState().mood).toEqual({
    courses: [],
    time: "any",
    moods: [],
    weather: [],
  });
  expect(api.searches[0]).toMatchObject({ courses: [], moods: [] });
});

test("the time choices read in order", async () => {
  await openMood();
  expect(
    screen.getAllByRole("radio").map((radio) => radio.closest("label")?.textContent),
  ).toEqual(["Any", "15 min", "30 min", "1 hr", "1 hr+"]);
});
