import type { Allergen, Diet, MoodPicks } from "../store/device";
import {
  ALLERGENS,
  COURSES_SHORT,
  DIET_CHOICES,
  dietChoice,
  MOODS,
  TIMES,
  WEATHER,
} from "./labels";

/**
 * The food rules chip on the deck, such as "Veg · No peanuts" or
 * "Jain · Avoiding 3". `ingredientName` names an avoided ingredient.
 */
export function foodRulesSummary(
  rules: {
    diet: Diet | null;
    jain: boolean;
    avoidAllergens: readonly Allergen[];
    avoidIngredients: readonly string[];
  },
  ingredientName: (id: string) => string | undefined,
): string {
  const choice = dietChoice(rules.diet, rules.jain);
  const diet = DIET_CHOICES.find((item) => item.id === choice)?.short ?? "Any diet";
  const avoided = [
    ...rules.avoidAllergens.map((allergen) => ALLERGENS[allergen]),
    ...rules.avoidIngredients.map((id) => ingredientName(id) ?? id),
  ];
  if (avoided.length === 0) return diet;
  if (avoided.length === 1) return `${diet} · No ${avoided[0]?.toLowerCase() ?? ""}`;
  return `${diet} · Avoiding ${String(avoided.length)}`;
}

/**
 * The mood chip on the deck: "Snacks · 30 min · Spicy, Tangy · Rainy-day
 * cosy" (ADR-0012 rule 12), or null with nothing picked.
 */
export function moodSummary(mood: MoodPicks): string | null {
  const parts = [
    mood.courses.map((course) => COURSES_SHORT[course]).join(", "),
    mood.time === "any" ? "" : TIMES[mood.time],
    mood.moods.map((item) => MOODS[item]).join(", "),
    mood.weather.map((item) => WEATHER[item]).join(", "),
  ].filter((part) => part !== "");
  return parts.length === 0 ? null : parts.join(" · ");
}

/** How many things the mood screen has picked; a time choice counts as one. */
export function pickedCount(mood: MoodPicks): number {
  return (
    mood.courses.length +
    mood.moods.length +
    mood.weather.length +
    (mood.time === "any" ? 0 : 1)
  );
}

/**
 * The picks for "Show more?" when the first deck runs short (ADR-0012 rule
 * 13): first without moods, then without courses; null when neither is left
 * to drop. Weather never filters and the time is kept, so neither is dropped.
 */
export function widened(mood: MoodPicks): MoodPicks | null {
  if (mood.moods.length > 0) return { ...mood, moods: [] };
  if (mood.courses.length > 0) return { ...mood, courses: [] };
  return null;
}
