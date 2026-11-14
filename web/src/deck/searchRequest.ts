import type { components } from "../api/schema";
import { timeLimits } from "../rules/labels";
import { type DeviceData, MAX_HIDDEN, type MoodPicks } from "../store/device";

export type SearchRequest = components["schemas"]["SearchRequest"];

/** Cards in one deck: the most the API deals at once. */
export const DECK_SIZE = 20;
/** The most pantry ids one search accepts. */
export const MAX_INGREDIENTS = 50;
/** The most out-of-stock staples one search accepts. */
export const MAX_EXCLUDED_STAPLES = 100;
/** The most avoided ingredients one search accepts. */
export const MAX_AVOIDED_INGREDIENTS = 50;

/**
 * The search for this device's pantry, food rules and the given mood picks,
 * or null when the pantry is empty. The mood is passed in, not read from the
 * device, because "Show more?" deals with fewer picks than were saved.
 *
 * Every saved id is sent, even ones the catalog no longer lists: ids are
 * never reused or deleted, so the API reports retired ones under
 * `ignored_ingredients` instead of refusing them (ADR-0006 rule 5).
 */
export function searchFor(
  device: Pick<
    DeviceData,
    | "pantry"
    | "outOfStaples"
    | "hidden"
    | "diet"
    | "jain"
    | "avoidAllergens"
    | "avoidIngredients"
  >,
  mood: MoodPicks,
): SearchRequest | null {
  if (device.pantry.length === 0) return null;
  return {
    limit: DECK_SIZE,
    // Past the limit, the newest additions win: they're what the user just did.
    ingredient_ids: device.pantry.slice(-MAX_INGREDIENTS),
    excluded_staples: device.outOfStaples.slice(-MAX_EXCLUDED_STAPLES),
    hidden_recipe_ids: device.hidden.slice(-MAX_HIDDEN),
    // The food rules (ADR-0012 rule 4). Jain needs a veg diet, which the
    // food rules screen always sets with it.
    diet: device.diet,
    jain: device.jain,
    avoid_allergens: device.avoidAllergens,
    avoid_ingredient_ids: device.avoidIngredients.slice(-MAX_AVOIDED_INGREDIENTS),
    // The mood screen (rule 5).
    ...timeLimits(mood.time),
    courses: mood.courses,
    moods: mood.moods,
    weather: mood.weather,
  };
}
