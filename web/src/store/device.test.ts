import { IDBFactory } from "fake-indexeddb";

import { createIdbStorage } from "./idbStorage";

import type { DeviceData } from "./device";

type DeviceModule = typeof import("./device");

/**
 * A fresh store on a fresh IndexedDB, optionally seeded with a saved blob,
 * as the app sees it on a cold start.
 */
async function coldStart(
  saved?: string,
  // Pass another tab's factory to open the same database in a second tab.
  factory = new IDBFactory(),
): Promise<{
  device: DeviceModule;
  stored: () => Promise<string | null>;
}> {
  const storage = createIdbStorage(factory);
  if (saved !== undefined) await storage.setItem("device", saved);
  vi.stubGlobal("indexedDB", factory);
  tabs.push(factory);
  vi.resetModules();
  const device = await import("./device");
  loaded.push(device);
  await vi.waitFor(() => {
    expect(device.useDevice.getState().hydration).not.toBe("pending");
  });
  return {
    device,
    stored: async () => {
      // Let the store's own write land first.
      await new Promise((resolve) => setTimeout(resolve, 20));
      return storage.getItem("device");
    },
  };
}

const tabs: IDBFactory[] = [];
const loaded: DeviceModule[] = [];

afterEach(() => {
  vi.unstubAllGlobals();
  tabs.length = 0;
  // Each test's stores stop listening, so they can't re-read in later tests.
  for (const device of loaded.splice(0)) device.stopSync();
});

const v1 = (pantry: string[], outOfStaples: string[] = []) =>
  JSON.stringify({ state: { pantry, outOfStaples }, version: 1 });

const v2 = (data: Partial<DeviceData>) =>
  JSON.stringify({
    state: { pantry: [], outOfStaples: [], saved: [], hidden: [], ...data },
    version: 2,
  });

const v3 = (data: Partial<DeviceData>) =>
  JSON.stringify({
    state: {
      pantry: [],
      outOfStaples: [],
      saved: [],
      hidden: [],
      diet: null,
      maxTotalMinutes: null,
      swipeHintSeen: false,
      ...data,
    },
    version: 3,
  });

const v4 = (data: Partial<DeviceData>) =>
  JSON.stringify({
    state: {
      pantry: [],
      outOfStaples: [],
      saved: [],
      hidden: [],
      diet: null,
      maxTotalMinutes: null,
      swipeHintSeen: false,
      voiceNoticeSeen: false,
      ...data,
    },
    version: 4,
  });

const v5 = (data: Partial<DeviceData>) =>
  JSON.stringify({
    state: {
      pantry: [],
      outOfStaples: [],
      saved: [],
      hidden: [],
      diet: null,
      maxTotalMinutes: null,
      swipeHintSeen: false,
      voiceNoticeSeen: false,
      installNudgeDismissed: false,
      ...data,
    },
    version: 5,
  });

test("a first visit starts empty and saves what the user adds", async () => {
  const { device, stored } = await coldStart();
  const { useDevice } = device;
  expect(useDevice.getState().hydration).toBe("ready");

  useDevice.getState().addToPantry(["milk"]);

  expect(await stored()).toBe(v5({ pantry: ["milk"] }));
});

test("a return visit gets back what was saved", async () => {
  const saved = {
    pantry: ["milk", "egg"],
    outOfStaples: ["salt"],
    saved: ["r1"],
    hidden: ["r2"],
    diet: "vegetarian" as const,
    maxTotalMinutes: 30,
    swipeHintSeen: true,
    voiceNoticeSeen: true,
    installNudgeDismissed: true,
  };
  const { device } = await coldStart(v5(saved));

  expect(device.useDevice.getState()).toMatchObject({ hydration: "ready", ...saved });
});

test("data saved before recipes existed (v1) is upgraded, not lost", async () => {
  const { device, stored } = await coldStart(v1(["milk", "egg"], ["salt"]));
  const { useDevice } = device;

  expect(useDevice.getState()).toMatchObject({
    hydration: "ready",
    pantry: ["milk", "egg"],
    outOfStaples: ["salt"],
    saved: [],
    hidden: [],
  });

  useDevice.getState().saveRecipe("r1");

  expect(await stored()).toBe(
    v5({
      pantry: ["milk", "egg"],
      outOfStaples: ["salt"],
      saved: ["r1"],
      swipeHintSeen: false,
    }),
  );
});

test.each([
  ["nothing swiped yet still gets the hint", {}, false],
  ["a save means the user has swiped", { saved: ["r1"] }, true],
  ["so does a skip", { hidden: ["r2"] }, true],
])("data saved before filters (v2) is upgraded: %s", async (_case, data, seen) => {
  const { device } = await coldStart(v2({ pantry: ["milk"], ...data }));

  expect(device.useDevice.getState()).toMatchObject({
    hydration: "ready",
    pantry: ["milk"],
    ...data,
    diet: null,
    maxTotalMinutes: null,
    swipeHintSeen: seen,
    voiceNoticeSeen: false,
  });
});

test("data saved before voice add (v3) is upgraded: nobody has seen its notice", async () => {
  const { device } = await coldStart(
    v3({ pantry: ["milk"], diet: "vegan", swipeHintSeen: true }),
  );

  expect(device.useDevice.getState()).toMatchObject({
    hydration: "ready",
    pantry: ["milk"],
    diet: "vegan",
    swipeHintSeen: true,
    voiceNoticeSeen: false,
    installNudgeDismissed: false,
  });
});

test("data saved before the install nudge (v4) is upgraded", async () => {
  const { device } = await coldStart(v4({ saved: ["r1"], voiceNoticeSeen: true }));

  expect(device.useDevice.getState()).toMatchObject({
    hydration: "ready",
    saved: ["r1"],
    voiceNoticeSeen: true,
    installNudgeDismissed: false,
  });
});

test.each([
  [
    "from a newer version of the app",
    JSON.stringify({ state: { pantry: ["milk"], saved: ["r1"], lists: [] }, version: 6 }),
  ],
  ["that isn't valid JSON", "{not json"],
])("data %s is never written over", async (_case, saved) => {
  const { device, stored } = await coldStart(saved);
  const { useDevice } = device;
  expect(useDevice.getState().hydration).toBe("failed");

  useDevice.getState().addToPantry(["potato"]);
  useDevice.getState().toggleStaple("salt");

  // The app still works for this visit, in memory...
  expect(useDevice.getState().pantry).toEqual(["potato"]);
  // ...but the data it couldn't read is exactly as it was.
  expect(await stored()).toBe(saved);
});

describe("actions", () => {
  let useDevice: DeviceModule["useDevice"];

  beforeEach(async () => {
    ({ useDevice } = (await coldStart()).device);
  });

  test("adding keeps the order the user added things in and skips repeats", () => {
    useDevice.getState().addToPantry(["milk", "egg"]);
    useDevice.getState().addToPantry(["egg", "potato"]);

    expect(useDevice.getState().pantry).toEqual(["milk", "egg", "potato"]);
  });

  test("removing and clearing the pantry", () => {
    useDevice.getState().addToPantry(["milk", "egg"]);
    useDevice.getState().removeFromPantry("milk");
    expect(useDevice.getState().pantry).toEqual(["egg"]);

    useDevice.getState().clearPantry();
    expect(useDevice.getState().pantry).toEqual([]);
  });

  test("saving and hiding keep the newest last, without repeats", () => {
    useDevice.getState().saveRecipe("r1");
    useDevice.getState().saveRecipe("r2");
    useDevice.getState().saveRecipe("r1");
    useDevice.getState().hideRecipe("r3");
    useDevice.getState().hideRecipe("r4");

    expect(useDevice.getState()).toMatchObject({
      saved: ["r2", "r1"],
      hidden: ["r3", "r4"],
    });

    useDevice.getState().unsaveRecipe("r2");
    useDevice.getState().unhideRecipe("r3");
    expect(useDevice.getState()).toMatchObject({ saved: ["r1"], hidden: ["r4"] });
  });

  test("saving a hidden recipe un-hides it", () => {
    useDevice.getState().hideRecipe("r1");
    useDevice.getState().saveRecipe("r1");

    expect(useDevice.getState()).toMatchObject({ saved: ["r1"], hidden: [] });
  });

  test("hiding a saved recipe never loses the save", () => {
    useDevice.getState().saveRecipe("r1");
    useDevice.getState().hideRecipe("r1");

    expect(useDevice.getState()).toMatchObject({ saved: ["r1"], hidden: [] });
  });

  test("past the API's limit the oldest hide is dropped", async () => {
    const { MAX_HIDDEN } = await import("./device");
    for (let index = 0; index <= MAX_HIDDEN; index++) {
      useDevice.getState().hideRecipe(`r${String(index)}`);
    }

    const { hidden } = useDevice.getState();
    expect(hidden).toHaveLength(MAX_HIDDEN);
    expect(hidden[0]).toBe("r1");
    expect(hidden.at(-1)).toBe(`r${String(MAX_HIDDEN)}`);
  });

  test("the first save asks the browser to keep this site's data", () => {
    const persist = vi.fn(() => Promise.resolve(true));
    vi.stubGlobal("navigator", { storage: { persist } });

    useDevice.getState().saveRecipe("r1");
    useDevice.getState().saveRecipe("r2");

    expect(persist).toHaveBeenCalledTimes(1);
  });

  test("filters are remembered for the next deck", () => {
    useDevice.getState().setFilters({ diet: "egg", maxTotalMinutes: 45 });
    expect(useDevice.getState()).toMatchObject({ diet: "egg", maxTotalMinutes: 45 });

    useDevice.getState().setFilters({ diet: null, maxTotalMinutes: null });
    expect(useDevice.getState()).toMatchObject({ diet: null, maxTotalMinutes: null });
  });

  test("the swipe hint, once seen, stays seen", () => {
    expect(useDevice.getState().swipeHintSeen).toBe(false);
    useDevice.getState().markSwipeHintSeen();
    useDevice.getState().markSwipeHintSeen();
    expect(useDevice.getState().swipeHintSeen).toBe(true);
  });

  test("toggling a staple marks it out of stock, then back in", () => {
    useDevice.getState().toggleStaple("salt");
    expect(useDevice.getState().outOfStaples).toEqual(["salt"]);

    useDevice.getState().toggleStaple("salt");
    expect(useDevice.getState().outOfStaples).toEqual([]);
  });
});

describe("two tabs", () => {
  test("each tab picks up what the other saved, so neither writes over it", async () => {
    const first = await coldStart();
    const second = await coldStart(undefined, tabs[0]);
    const a = first.device.useDevice;
    const b = second.device.useDevice;

    a.getState().addToPantry(["milk"]);
    await vi.waitFor(() => {
      expect(b.getState().pantry).toEqual(["milk"]);
    });

    b.getState().saveRecipe("r1");
    await vi.waitFor(() => {
      expect(a.getState().saved).toEqual(["r1"]);
    });

    a.getState().addToPantry(["egg"]);

    expect(await second.stored()).toBe(v5({ pantry: ["milk", "egg"], saved: ["r1"] }));
  });
});

describe("announceWrites", () => {
  test("announces real changes and skips writes of what's already stored", async () => {
    const { announceWrites } = await import("./device");
    const memory = new Map<string, string>([["device", "a"]]);
    const announce = vi.fn();
    const storage = announceWrites(
      {
        getItem: (name) => memory.get(name) ?? null,
        setItem: (name, value) => {
          memory.set(name, value);
        },
        removeItem: (name) => {
          memory.delete(name);
        },
      },
      announce,
    );

    await storage.getItem("device");
    await storage.setItem("device", "a");
    expect(announce).not.toHaveBeenCalled();

    await storage.setItem("device", "b");
    expect(announce).toHaveBeenCalledTimes(1);
    expect(memory.get("device")).toBe("b");
  });
});
