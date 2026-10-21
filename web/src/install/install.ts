import { useSyncExternalStore } from "react";

/** Chrome's install prompt event; TypeScript's DOM lib lacks it. */
export interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/**
 * How this browser can add the app to the home screen: "prompt" when Chrome
 * or Edge offered its install dialog, else null.
 *
 * iPhone and iPad never get a tip: a home-screen app there starts with empty
 * storage, separate from Safari's, so installing would hide the user's saves
 * (issue #55; Nisha chose to hide it until accounts in v2).
 */
export type InstallWay = "prompt" | null;

let deferred: InstallPromptEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();

function changed() {
  for (const listener of listeners) listener();
}

/**
 * Chrome fires `beforeinstallprompt` once, often before any screen mounts, so
 * it's caught here, when the app loads, and kept until the nudge asks for it.
 */
export function watchInstall(scope: Window = window): void {
  scope.addEventListener("beforeinstallprompt", (event) => {
    // Hold Chrome's own mini-infobar back: the nudge offers it at a better time.
    event.preventDefault();
    deferred = event as InstallPromptEvent;
    changed();
  });
  scope.addEventListener("appinstalled", () => {
    deferred = null;
    installed = true;
    changed();
  });
}

function runningInstalled(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function installWay(): InstallWay {
  if (installed || runningInstalled()) return null;
  return deferred ? "prompt" : null;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useInstallWay(): InstallWay {
  return useSyncExternalStore(subscribe, installWay);
}

/** Shows Chrome's install dialog. True if the user installed. */
export async function promptInstall(): Promise<boolean> {
  const event = deferred;
  if (!event) return false;
  // The event can be used once; Chrome fires a new one if it's declined.
  deferred = null;
  changed();
  await event.prompt();
  const { outcome } = await event.userChoice;
  return outcome === "accepted";
}

/** Forgets everything caught so far. Tests call it between cases. */
export function resetInstall(): void {
  deferred = null;
  installed = false;
  changed();
}
