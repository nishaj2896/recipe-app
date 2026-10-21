import { IDBFactory } from "fake-indexeddb";

import { createIdbStorage } from "./idbStorage";

test("values survive in IndexedDB between storage instances", async () => {
  const factory = new IDBFactory();
  await createIdbStorage(factory).setItem("device", '{"a":1}');

  expect(await createIdbStorage(factory).getItem("device")).toBe('{"a":1}');
});

test("removing a value forgets it", async () => {
  const storage = createIdbStorage(new IDBFactory());
  await storage.setItem("device", "x");
  await storage.removeItem("device");

  expect(await storage.getItem("device")).toBeNull();
});

test("without IndexedDB, values live in memory for the visit", async () => {
  const storage = createIdbStorage(null);
  await storage.setItem("device", "x");

  expect(await storage.getItem("device")).toBe("x");
});
