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
}

export type DeviceState = DeviceData & DeviceActions & { hydration: Hydration };

export const DEVICE_STORE_NAME = "device";
export const DEVICE_STORE_VERSION = 1;

export const emptyDevice: DeviceData = { pantry: [], outOfStaples: [] };

/**
 * Upgrades data saved by an older version of the app. Each future version
 * adds a step here. A version it doesn't know (say, from a newer build after
 * a rollback) is refused, never guessed at: the store then stays read-only.
 */
export function migrateDevice(saved: unknown, version: number): DeviceData {
  if (version === DEVICE_STORE_VERSION) return saved as DeviceData;
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

let readSucceeded = false;

export const useDevice = create<DeviceState>()(
  persist(
    (set) => ({
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
    }),
    {
      name: DEVICE_STORE_NAME,
      version: DEVICE_STORE_VERSION,
      storage: createJSONStorage(() =>
        writeAfterRead(createIdbStorage(), () => readSucceeded),
      ),
      partialize: ({ pantry, outOfStaples }): DeviceData => ({ pantry, outOfStaples }),
      migrate: migrateDevice,
      onRehydrateStorage: () => (_state, error) => {
        readSucceeded = error === undefined;
        useDevice.setState({ hydration: readSucceeded ? "ready" : "failed" });
      },
    },
  ),
);
