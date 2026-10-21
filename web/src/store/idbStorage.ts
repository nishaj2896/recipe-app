import type { StateStorage } from "zustand/middleware";

const DB_NAME = "recipe-app";
const STORE = "keyval";

function openDatabase(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE);
    };
    request.onsuccess = () => {
      resolve(request.result);
    };
    request.onerror = () => {
      reject(request.error ?? new Error("could not open IndexedDB"));
    };
  });
}

function run<T>(
  db: IDBDatabase,
  mode: IDBTransactionMode,
  body: (store: IDBObjectStore) => IDBRequest,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const request = body(transaction.objectStore(STORE));
    transaction.oncomplete = () => {
      resolve(request.result as T);
    };
    transaction.onerror = () => {
      reject(transaction.error ?? new Error("IndexedDB transaction failed"));
    };
  });
}

/**
 * A key-value store on IndexedDB for Zustand's persist middleware (ADR-0006
 * rule 5). IndexedDB is asynchronous, so a write never blocks a swipe.
 *
 * Where IndexedDB is unavailable (some private modes), state lives in memory
 * for the visit: the app still works, it just forgets on reload.
 */
export function createIdbStorage(
  // Typed as optional on purpose: some private modes have no IndexedDB at all.
  factory: IDBFactory | null = "indexedDB" in globalThis ? globalThis.indexedDB : null,
): StateStorage {
  const memory = new Map<string, string>();
  const db = factory ? openDatabase(factory).catch(() => null) : Promise.resolve(null);

  return {
    async getItem(name) {
      const handle = await db;
      if (!handle) return memory.get(name) ?? null;
      const value = await run<unknown>(handle, "readonly", (store) => store.get(name));
      return typeof value === "string" ? value : null;
    },
    async setItem(name, value) {
      const handle = await db;
      if (!handle) {
        memory.set(name, value);
        return;
      }
      await run(handle, "readwrite", (store) => store.put(value, name));
    },
    async removeItem(name) {
      const handle = await db;
      if (!handle) {
        memory.delete(name);
        return;
      }
      await run(handle, "readwrite", (store) => store.delete(name));
    },
  };
}
