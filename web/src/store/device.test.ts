import { DEVICE_STORE_VERSION, emptyDevice, migrateDevice, useDevice } from "./device";

beforeEach(() => {
  useDevice.setState(emptyDevice);
});

const actions = () => useDevice.getState();

test("adding keeps the order the user added things in and skips repeats", () => {
  actions().addToPantry(["milk", "egg"]);
  actions().addToPantry(["egg", "potato"]);

  expect(useDevice.getState().pantry).toEqual(["milk", "egg", "potato"]);
});

test("removing and clearing the pantry", () => {
  actions().addToPantry(["milk", "egg"]);
  actions().removeFromPantry("milk");
  expect(useDevice.getState().pantry).toEqual(["egg"]);

  actions().clearPantry();
  expect(useDevice.getState().pantry).toEqual([]);
});

test("toggling a staple marks it out of stock, then back in", () => {
  actions().toggleStaple("salt");
  expect(useDevice.getState().outOfStaples).toEqual(["salt"]);

  actions().toggleStaple("salt");
  expect(useDevice.getState().outOfStaples).toEqual([]);
});

test("the pantry is written to the device", async () => {
  actions().addToPantry(["milk"]);

  const saved = await useDevice.persist.getOptions().storage?.getItem("device");
  expect(saved).toEqual({
    state: { pantry: ["milk"], outOfStaples: [] },
    version: DEVICE_STORE_VERSION,
  });
});

test("data from a version the app doesn't know is refused, not guessed at", () => {
  expect(() => migrateDevice({ pantry: ["milk"] }, 0)).toThrow(/no migration/);
});
