import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { stubApi } from "../test/api";
import { emptyDevice, useDevice } from "../store/device";

// The cookbook's code can't be fetched: a dropped connection, or a deploy
// that renamed the file while the app was open.
vi.mock("../cookbook/CookbookScreen", () => {
  throw new Error("Failed to fetch dynamically imported module");
});

beforeEach(() => {
  useDevice.setState({ ...emptyDevice, hydration: "ready" });
  window.history.pushState({}, "", "/saved");
  // React reports the caught error; it's expected here.
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("a screen that can't load offers a reload instead of a blank page", async () => {
  stubApi();
  render(<App />);

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Couldn't load this screen");
  // The rest of the app is still there.
  expect(document.querySelector("svg")).toBeInTheDocument();

  const reload = vi.fn();
  vi.stubGlobal("location", { href: window.location.href, reload });
  await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
  expect(reload).toHaveBeenCalledTimes(1);
});
