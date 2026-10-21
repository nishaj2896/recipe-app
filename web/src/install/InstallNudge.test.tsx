import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { DECK, stubApi } from "../test/api";
import { resetInstall, watchInstall } from "./install";

watchInstall(window);

beforeEach(() => {
  stubApi();
  useDevice.setState({
    ...emptyDevice,
    pantry: ["paneer"],
    saved: [DECK[0]?.id ?? ""],
    hydration: "ready",
  });
  window.history.pushState({}, "", "/saved");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetInstall();
});

/** Chrome offering to install, as `beforeinstallprompt`. */
function offerInstall(outcome: "accepted" | "dismissed" = "accepted") {
  const prompt = vi.fn(() => Promise.resolve());
  const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
    prompt,
    userChoice: Promise.resolve({ outcome }),
  });
  act(() => {
    window.dispatchEvent(event);
  });
  return { prompt, event };
}

const nudge = () => screen.queryByRole("complementary", { name: "Add to home screen" });

test("once Chrome offers to install, the cookbook suggests it, and Install opens the dialog", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("heading", { name: "Your cookbook" });
  expect(nudge()).toBeNull();

  const { prompt, event } = offerInstall();
  // Chrome's own mini-infobar is held back.
  expect(event.defaultPrevented).toBe(true);
  expect(nudge()).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Install" }));

  expect(prompt).toHaveBeenCalledTimes(1);
  // The event is spent: the nudge goes until Chrome offers again.
  expect(nudge()).toBeNull();
});

test("Not now hides the nudge for good", async () => {
  const user = userEvent.setup();
  render(<App />);
  offerInstall();

  await user.click(await screen.findByRole("button", { name: "Not now" }));

  expect(nudge()).toBeNull();
  expect(useDevice.getState().installNudgeDismissed).toBe(true);
});

test("on an iPhone it explains Share, then Add to Home Screen", async () => {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
  );
  render(<App />);

  expect(
    await screen.findByText(/tap Share, then Add to Home Screen/),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Install" })).toBeNull();
});

test("nothing is suggested before the first save, or once installed", async () => {
  useDevice.setState({ saved: [] });
  render(<App />);
  offerInstall();
  await screen.findByText(/Recipes you swipe right on land here/);
  expect(nudge()).toBeNull();

  act(() => {
    useDevice.setState({ saved: [DECK[0]?.id ?? ""] });
  });
  expect(nudge()).toBeInTheDocument();

  act(() => {
    window.dispatchEvent(new Event("appinstalled"));
  });
  expect(nudge()).toBeNull();
});
