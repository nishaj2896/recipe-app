import type { Diet } from "../store/device";

/**
 * The diets a deck can be limited to, strictest last. Each lets through every
 * stricter one: vegetarian includes vegan (ADR-0002 rule 6). Non-veg allows
 * everything, so it is "any".
 */
export const DIET_OPTIONS: readonly {
  value: Diet | null;
  label: string;
  short: string;
}[] = [
  { value: null, label: "Anything", short: "Any diet" },
  { value: "egg", label: "Vegetarian + egg", short: "Veg + egg" },
  { value: "vegetarian", label: "Vegetarian", short: "Veg" },
  { value: "vegan", label: "Vegan", short: "Vegan" },
];

/** Total-time limits, in minutes. */
export const TIME_OPTIONS: readonly (number | null)[] = [null, 15, 30, 45, 60];

export function timeLabel(minutes: number | null): string {
  return minutes === null ? "Any time" : `≤${String(minutes)} min`;
}

/** The filter chip's text, such as "Veg · ≤30 min". */
export function filterSummary(diet: Diet | null, maxTotalMinutes: number | null): string {
  const short = DIET_OPTIONS.find((option) => option.value === diet)?.short ?? "Any diet";
  return `${short} · ${timeLabel(maxTotalMinutes)}`;
}
