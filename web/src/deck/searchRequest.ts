import type { components } from "../api/schema";
import { type DeviceData, MAX_HIDDEN } from "../store/device";

export type SearchRequest = components["schemas"]["SearchRequest"];

/** Cards in one deck: the most the API deals at once. */
export const DECK_SIZE = 20;
/** The most pantry ids one search accepts. */
export const MAX_INGREDIENTS = 50;
/** The most out-of-stock staples one search accepts. */
export const MAX_EXCLUDED_STAPLES = 100;

/**
 * The search for this device's pantry, or null when the pantry is empty.
 *
 * Every saved id is sent, even ones the catalog no longer lists: ids are
 * never reused or deleted, so the API reports retired ones under
 * `ignored_ingredients` instead of refusing them (ADR-0006 rule 5).
 */
export function searchFor(
  device: Pick<
    DeviceData,
    "pantry" | "outOfStaples" | "hidden" | "diet" | "maxTotalMinutes"
  >,
): SearchRequest | null {
  if (device.pantry.length === 0) return null;
  return {
    limit: DECK_SIZE,
    // Past the limit, the newest additions win: they're what the user just did.
    ingredient_ids: device.pantry.slice(-MAX_INGREDIENTS),
    excluded_staples: device.outOfStaples.slice(-MAX_EXCLUDED_STAPLES),
    hidden_recipe_ids: device.hidden.slice(-MAX_HIDDEN),
    diet: device.diet,
    max_total_minutes: device.maxTotalMinutes,
  };
}
