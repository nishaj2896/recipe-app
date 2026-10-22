import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

import type { components } from "../api/schema";
import { createIdbStorage } from "./idbStorage";

export type Diet = components["schemas"]["Diet"];

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
  /** The strictest diet a deck may deal, or null for any. */
  diet: Diet | null;
  /** The longest total time a deck may deal, in minutes, or null for any. */
  maxTotalMinutes: number | null;
  /** Whether the user has swiped once, so the first-run hint never shows again. */
  swipeHintSeen: boolean;
  /**
   * Whether the user has been told, before their first use of the mic, that
   * the browser sends what they say to its speech service.
   */
  voiceNoticeSeen: boolean;
  /** Whether the user said "Not now" to adding the app to their home screen. */
  installNudgeDismissed: boolean;
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
  clearSaved: () => void;
  /** Puts the saved list back as it was, to undo a removal. */
  restoreSaved: (ids: readonly string[]) => void;
  hideRecipe: (id: string) => void;
  unhideRecipe: (id: string) => void;
  setFilters: (filters: Pick<DeviceData, "diet" | "maxTotalMinutes">) => void;
  markSwipeHintSeen: () => void;
  markVoiceNoticeSeen: () => void;
  dismissInstallNudge: () => void;
}

export type DeviceState = DeviceData & DeviceActions & { hydration: Hydration };

export const DEVICE_STORE_NAME = "device";
export const DEVICE_STORE_VERSION = 5;
/** The most hidden ids the search API accepts (ADR-0006 rule 5). */
export const MAX_HIDDEN = 200;

export const emptyDevice: DeviceData = {
  pantry: [],
  outOfStaples: [],
  saved: [],
  hidden: [],
  diet: null,
  maxTotalMinutes: null,
  swipeHintSeen: false,
  voiceNoticeSeen: false,
  installNudgeDismissed: false,
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
  // v4 had no install nudge.
  if (version === 4) return { ...(stored as DeviceData), installNudgeDismissed: false };
  // v3 had no voice add, so nobody has seen its notice.
  if (version === 3)
    return migrateDevice({ ...(stored as DeviceData), voiceNoticeSeen: false }, 4);
  // v2 had no filters and no hint. Someone with saves has clearly swiped.
  if (version === 2) {
    const v2 = stored as DeviceData;
    return migrateDevice(
      {
        ...v2,
        diet: null,
        maxTotalMinutes: null,
        swipeHintSeen: v2.saved.length > 0 || v2.hidden.length > 0,
      },
      3,
    );
  }
  // v1 had no recipes yet.
  if (version === 1)
    return migrateDevice({ ...(stored as object), saved: [], hidden: [] }, 2);
  throw new Error(`no migration from device store version ${String(version)}`);
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
      clearSaved: () => {
        set({ saved: [] });
      },
      restoreSaved: (ids) => {
        set((state) => ({
          saved: [...ids],
          // A recipe saved again is no longer skipped.
          hidden: state.hidden.filter((id) => !ids.includes(id)),
        }));
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
      setFilters: ({ diet, maxTotalMinutes }) => {
        set({ diet, maxTotalMinutes });
      },
      markSwipeHintSeen: () => {
        set((state) => (state.swipeHintSeen ? state : { swipeHintSeen: true }));
      },
      markVoiceNoticeSeen: () => {
        set((state) => (state.voiceNoticeSeen ? state : { voiceNoticeSeen: true }));
      },
      dismissInstallNudge: () => {
        set({ installNudgeDismissed: true });
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
      partialize: ({
        pantry,
        outOfStaples,
        saved,
        hidden,
        diet,
        maxTotalMinutes,
        swipeHintSeen,
        voiceNoticeSeen,
        installNudgeDismissed,
      }): DeviceData => ({
        pantry,
        outOfStaples,
        saved,
        hidden,
        diet,
        maxTotalMinutes,
        swipeHintSeen,
        voiceNoticeSeen,
        installNudgeDismissed,
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
