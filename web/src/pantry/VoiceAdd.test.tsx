import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { emptyDevice, useDevice } from "../store/device";
import { stubApi } from "../test/api";
import { speechLanguage, useSpeech } from "./speech";

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
  useDevice.setState({
    ...emptyDevice,
    pantry: ["egg"],
    voiceNoticeSeen: true,
    hydration: "ready",
  });
  FakeRecognition.last = null;
  window.history.pushState({}, "", "/");
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

/** Like Safari at times: stop() is ignored and "end" never comes. */
class StubbornRecognition extends FakeRecognition {
  aborted = false;

  override stop() {
    // Keeps listening.
  }

  override abort() {
    this.aborted = true;
  }
}

test("tapping the mic again turns it off, even when the browser ignores stop", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("webkitSpeechRecognition", StubbornRecognition);
  const user = await openApp();
  const recognition = (await speak(user)) as StubbornRecognition;
  act(() => {
    recognition.hear("I have milk", false);
  });

  await user.click(screen.getByRole("button", { name: "Stop listening" }));
  act(() => {
    vi.advanceTimersByTime(1000);
  });

  expect(recognition.aborted).toBe(true);
  expect(screen.getByRole("button", { name: "Say what you have" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  vi.useRealTimers();
});

test("a finished sentence turns the mic off by itself", async () => {
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  const user = await openApp();
  const recognition = await speak(user);

  act(() => {
    recognition.hear("I have milk", true);
  });

  expect(useDevice.getState().pantry).toEqual(["egg", "milk"]);
  expect(screen.getByRole("button", { name: "Say what you have" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("a stop that ended one sentence never cuts the next one short", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  const user = await openApp();
  const first = await speak(user);
  act(() => {
    first.hear("I have milk", true);
  });

  const second = await speak(user);
  act(() => {
    second.hear("and paneer", false);
    vi.advanceTimersByTime(1100);
  });

  expect(screen.getByRole("button", { name: "Stop listening" })).toBeInTheDocument();
  vi.useRealTimers();
});

test("English speakers are heard as Indian English", () => {
  expect(speechLanguage("en-US")).toBe("en-IN");
  expect(speechLanguage("en")).toBe("en-IN");
  expect(speechLanguage("hi-IN")).toBe("hi-IN");
  expect(speechLanguage("")).toBe("en-IN");
});

test("leaving the screen mid-sentence delivers nothing", () => {
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  const onSentence = vi.fn();
  function Mic() {
    const speech = useSpeech(onSentence);
    return (
      <button type="button" onClick={speech.start}>
        Talk
      </button>
    );
  }
  const { unmount } = render(<Mic />);
  act(() => {
    screen.getByRole("button", { name: "Talk" }).click();
  });
  act(() => {
    FakeRecognition.last?.hear("potatoes and milk", false);
  });

  // Unmounting aborts, and an aborted recognition still fires "end".
  unmount();

  expect(onSentence).not.toHaveBeenCalled();
});

test("the mic waits for the ingredients to load", async () => {
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  render(<App />);

  expect(screen.queryByRole("button", { name: "Say what you have" })).toBeNull();
  expect(await screen.findByRole("button", { name: "Say what you have" })).toBeEnabled();
});

test("the first tap explains where the voice goes, and listens only after OK", async () => {
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  useDevice.setState({ voiceNoticeSeen: false });
  const user = await openApp();

  await user.click(screen.getByRole("button", { name: "Say what you have" }));
  const notice = await screen.findByRole("dialog", { name: "Before you speak" });
  expect(notice).toHaveTextContent(
    "Your browser sends what you say to its speech service (for example Google or Apple)",
  );
  expect(FakeRecognition.last).toBeNull();

  await user.click(within(notice).getByRole("button", { name: "OK, start listening" }));

  expect(FakeRecognition.last?.started).toBe(true);
  expect(useDevice.getState().voiceNoticeSeen).toBe(true);
});

test("closing the notice without OK doesn't listen, and it shows again next time", async () => {
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  useDevice.setState({ voiceNoticeSeen: false });
  const user = await openApp();

  await user.click(screen.getByRole("button", { name: "Say what you have" }));
  const notice = await screen.findByRole("dialog", { name: "Before you speak" });
  await user.click(within(notice).getByRole("button", { name: "Done" }));

  expect(FakeRecognition.last).toBeNull();
  expect(useDevice.getState().voiceNoticeSeen).toBe(false);
  await user.click(screen.getByRole("button", { name: "Say what you have" }));
  expect(await screen.findByRole("dialog", { name: "Before you speak" })).toBeVisible();
});
