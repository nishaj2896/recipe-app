import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { stubApi } from "../test/api";

/** A stand-in for the browser's speech recognition, driven by the test. */
class FakeRecognition extends EventTarget {
  static last: FakeRecognition | null = null;
  lang = "";
  interimResults = false;
  continuous = true;
  started = false;

  constructor() {
    super();
    FakeRecognition.last = this;
  }

  start() {
    this.started = true;
  }

  stop() {
    this.dispatchEvent(new Event("end"));
  }

  abort() {
    this.dispatchEvent(new Event("end"));
  }

  /** The browser heard `text`; `isFinal` once the speaker has stopped. */
  hear(text: string, isFinal: boolean) {
    const result = Object.assign([{ transcript: text }], { isFinal });
    this.dispatchEvent(Object.assign(new Event("result"), { results: [result] }));
  }

  fail(error: string) {
    this.dispatchEvent(Object.assign(new Event("error"), { error }));
    this.dispatchEvent(new Event("end"));
  }
}

beforeEach(() => {
  stubApi();
  useDevice.setState({ ...emptyDevice, pantry: ["egg"], hydration: "ready" });
  FakeRecognition.last = null;
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

async function speak(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Say what you have" }));
  const recognition = FakeRecognition.last;
  if (!recognition) throw new Error("recognition never started");
  return recognition;
}

test("browsers without speech recognition get no mic", async () => {
  await openApp();
  expect(screen.queryByRole("button", { name: "Say what you have" })).toBeNull();
});

test("saying what you have adds it, and says what was added", async () => {
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  const user = await openApp();
  const recognition = await speak(user);
  expect(recognition.started).toBe(true);
  expect(screen.getByRole("button", { name: "Stop listening" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByText("Listening… say what you have")).toBeInTheDocument();

  act(() => {
    recognition.hear("I have sweet potatoes", false);
  });
  expect(screen.getByText("“I have sweet potatoes”")).toBeInTheDocument();
  act(() => {
    recognition.hear("I have sweet potatoes, eggs, onions and milk", true);
    recognition.stop();
  });

  expect(useDevice.getState().pantry).toEqual(["egg", "sweet-potato", "milk"]);
  expect(
    screen.getByText(
      "Added sweet potato and milk. Egg was already in. Onion is a staple: we assume you have it.",
    ),
  ).toHaveAttribute("role", "status");
  expect(screen.getByRole("button", { name: "Say what you have" })).toBeInTheDocument();
});

test("a sentence naming no ingredient says so", async () => {
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  const user = await openApp();
  const recognition = await speak(user);

  act(() => {
    recognition.hear("what's for dinner", true);
    recognition.stop();
  });

  expect(
    screen.getByText(/We didn't find an ingredient in “what's for dinner”/),
  ).toBeInTheDocument();
  expect(useDevice.getState().pantry).toEqual(["egg"]);
});

test("a blocked microphone is explained, and nothing is added", async () => {
  vi.stubGlobal("SpeechRecognition", FakeRecognition);
  const user = await openApp();
  const recognition = await speak(user);

  act(() => {
    recognition.fail("not-allowed");
  });

  expect(
    screen.getByText("The microphone is off for this site. You can type instead."),
  ).toBeInTheDocument();
  expect(useDevice.getState().pantry).toEqual(["egg"]);
});
