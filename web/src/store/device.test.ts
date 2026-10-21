import { IDBFactory } from "fake-indexeddb";

import { createIdbStorage } from "./idbStorage";

type DeviceModule = typeof import("./device");

/**
 * A fresh store on a fresh IndexedDB, optionally seeded with a saved blob,
 * as the app sees it on a cold start.
 */
async function coldStart(saved?: string): Promise<{
  device: DeviceModule;
  stored: () => Promise<string | null>;
}> {
  const factory = new IDBFactory();
  const storage = createIdbStorage(factory);
  if (saved !== undefined) await storage.setItem("device", saved);
  vi.stubGlobal("indexedDB", factory);
  vi.resetModules();
  const device = await import("./device");
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

afterEach(() => {
  vi.unstubAllGlobals();
});

const v1 = (pantry: string[], outOfStaples: string[] = []) =>
  JSON.stringify({ state: { pantry, outOfStaples }, version: 1 });

test("a first visit starts empty and saves what the user adds", async () => {
  const { device, stored } = await coldStart();
  const { useDevice } = device;
  expect(useDevice.getState().hydration).toBe("ready");

  useDevice.getState().addToPantry(["milk"]);

  expect(await stored()).toBe(v1(["milk"]));
});

test("a return visit gets back what was saved", async () => {
  const { device } = await coldStart(v1(["milk", "egg"], ["salt"]));

  expect(device.useDevice.getState()).toMatchObject({
    hydration: "ready",
    pantry: ["milk", "egg"],
    outOfStaples: ["salt"],
  });
});

test.each([
  [
    "from a newer version of the app",
    JSON.stringify({ state: { pantry: ["milk"], saved: ["r1"] }, version: 2 }),
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

  test("toggling a staple marks it out of stock, then back in", () => {
    useDevice.getState().toggleStaple("salt");
    expect(useDevice.getState().outOfStaples).toEqual(["salt"]);

    useDevice.getState().toggleStaple("salt");
    expect(useDevice.getState().outOfStaples).toEqual([]);
  });
});
