import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

import { createIdbStorage } from "./idbStorage";

/**
 * What this device remembers between visits (ADR-0006 rule 5). v1 has no
 * accounts, so this is the only copy: change the shape only with a version
 * bump and a migration.
 */
export interface DeviceData {
  /** Ingredient ids the user has, in the order they added them. */
  pantry: string[];
  /** Staple ids the user unticked: they're out of them right now. */
  outOfStaples: string[];
  /**
   * Recipe ids the user swiped right on, oldest first. Never pruned, and an id
   * is never in both lists: saving un-hides, and hiding a saved id does nothing.
   */
  saved: string[];
  /** Recipe ids the user swiped left on, oldest first: the newest 200 at most. */
  hidden: string[];
}

/**
 * Where reading the saved data has got to. Until it is "ready" nothing is
 * written, so a failed read can never be followed by a write over the data
 * the app couldn't read.
 */
export type Hydration = "pending" | "ready" | "failed";

interface DeviceActions {
  addToPantry: (ids: readonly string[]) => void;
  removeFromPantry: (id: string) => void;
  clearPantry: () => void;
  toggleStaple: (id: string) => void;
  saveRecipe: (id: string) => void;
  unsaveRecipe: (id: string) => void;
  hideRecipe: (id: string) => void;
  unhideRecipe: (id: string) => void;
}

export type DeviceState = DeviceData & DeviceActions & { hydration: Hydration };

export const DEVICE_STORE_NAME = "device";
export const DEVICE_STORE_VERSION = 2;
/** The most hidden ids the search API accepts (ADR-0006 rule 5). */
export const MAX_HIDDEN = 200;

export const emptyDevice: DeviceData = {
  pantry: [],
  outOfStaples: [],
  saved: [],
  hidden: [],
};

/** Moves an id to the end of a list, so the list stays oldest first. */
const toEnd = (list: readonly string[], id: string) => [
  ...list.filter((item) => item !== id),
  id,
];
const without = (list: readonly string[], id: string) =>
  list.filter((item) => item !== id);

/**
 * Upgrades data saved by an older version of the app. Each future version
 * adds a step here. A version it doesn't know (say, from a newer build after
 * a rollback) is refused, never guessed at: the store then stays read-only.
 */
export function migrateDevice(stored: unknown, version: number): DeviceData {
  if (version === DEVICE_STORE_VERSION) return stored as DeviceData;
  // v1 had no recipes yet.
  if (version === 1) return { ...(stored as DeviceData), saved: [], hidden: [] };
  throw new Error(`no migration from device store version ${version}`);
}

/**
 * Passes writes through only once the saved data has been read successfully.
 * zustand's persist writes on every change even after a failed read, which
 * would replace data it couldn't read with an empty state.
 */
export function writeAfterRead(
  storage: StateStorage,
  canWrite: () => boolean,
): StateStorage {
  return {
    getItem: (name) => storage.getItem(name),
    setItem: (name, value) => (canWrite() ? storage.setItem(name, value) : undefined),
    removeItem: (name) => (canWrite() ? storage.removeItem(name) : undefined),
  };
}

/**
 * Tells the app's other tabs when this one has written, so they re-read
 * instead of later writing their stale copy over it (issue #44).
 *
 * A write that wouldn't change what's stored is skipped, and so is its
 * message: re-reading sets state, which would otherwise write, which would
 * wake the other tab, and so on forever.
 */
export function announceWrites(
  storage: StateStorage,
  announce: () => void,
): StateStorage {
  let known: string | null = null;
  return {
    getItem: async (name) => {
      known = await storage.getItem(name);
      return known;
    },
    setItem: async (name, value) => {
      if (value === known) return;
      known = value;
      await storage.setItem(name, value);
      announce();
    },
    removeItem: async (name) => {
      known = null;
      await storage.removeItem(name);
      announce();
    },
  };
}

let channel =
  "BroadcastChannel" in globalThis ? new BroadcastChannel("recipe-app:device") : null;

let readSucceeded = false;

export const useDevice = create<DeviceState>()(
  persist(
    (set, get) => ({
      ...emptyDevice,
      hydration: "pending",
      addToPantry: (ids) => {
        set((state) => {
          const pantry = [...new Set([...state.pantry, ...ids])];
          return pantry.length === state.pantry.length ? state : { pantry };
        });
      },
      removeFromPantry: (id) => {
        set((state) => ({ pantry: state.pantry.filter((item) => item !== id) }));
      },
      clearPantry: () => {
        set({ pantry: [] });
      },
      toggleStaple: (id) => {
        set((state) => ({
          outOfStaples: state.outOfStaples.includes(id)
            ? state.outOfStaples.filter((item) => item !== id)
            : [...state.outOfStaples, id],
        }));
      },
      saveRecipe: (id) => {
        // The first save asks the browser to keep this site's storage
        // (ADR-0006 rule 5); browsers without the API just carry on.
        if (get().saved.length === 0)
          void (navigator.storage as StorageManager | undefined)?.persist();
        set((state) => ({
          saved: toEnd(state.saved, id),
          hidden: without(state.hidden, id),
        }));
      },
      unsaveRecipe: (id) => {
        set((state) => ({ saved: without(state.saved, id) }));
      },
      hideRecipe: (id) => {
        set((state) =>
          // A save is never undone by accident (ADR-0006 rule 5): only
          // unsaving removes it.
          state.saved.includes(id)
            ? state
            : // The oldest hide falls off past the API's limit.
              { hidden: toEnd(state.hidden, id).slice(-MAX_HIDDEN) },
        );
      },
      unhideRecipe: (id) => {
        set((state) => ({ hidden: without(state.hidden, id) }));
      },
    }),
    {
      name: DEVICE_STORE_NAME,
      version: DEVICE_STORE_VERSION,
      storage: createJSONStorage(() =>
        writeAfterRead(
          announceWrites(createIdbStorage(), () => {
            channel?.postMessage("written");
          }),
          () => readSucceeded,
        ),
      ),
      partialize: ({ pantry, outOfStaples, saved, hidden }): DeviceData => ({
        pantry,
        outOfStaples,
        saved,
        hidden,
      }),
      migrate: migrateDevice,
      onRehydrateStorage: () => (_state, error) => {
        readSucceeded = error === undefined;
        useDevice.setState({ hydration: readSucceeded ? "ready" : "failed" });
      },
    },
  ),
);

// Another tab wrote: take its copy. Two tabs acting in the same instant can
// still race, and the later write wins; with one person on one phone that's
// rare, and accounts in v2 replace this.
function onOtherTabWrite() {
  void useDevice.persist.rehydrate();
}
channel?.addEventListener("message", onOtherTabWrite);

/** Stops listening to other tabs. Tests call it, so old stores stop re-reading. */
export function stopSync(): void {
  channel?.close();
  // A write still in flight then announces nothing, rather than posting on a
  // closed channel, which throws.
  channel = null;
}
