import type { RecipeCard } from "../api/client";
import { listNames } from "./names";
import type { Direction } from "./swipe";

/** A card as a screen reader hears it: "Aloo Gobi, 67% match, missing cauliflower". */
export function describeCard(card: RecipeCard): string {
  const match =
    card.match_percentage === null
      ? "pantry basics"
      : `${String(Math.round(card.match_percentage))}% match`;
  const missing =
    card.missing_ingredients.length > 0
      ? `missing ${listNames(card.missing_ingredients)}`
      : "nothing missing";
  return `${card.name}, ${match}, ${missing}`;
}

/** What a screen reader is told after a swipe, and which card is next. */
export function swipeMessage(
  card: RecipeCard,
  direction: Direction,
  next: RecipeCard | undefined,
): string {
  const done = `${direction === "right" ? "Saved" : "Skipped"} ${card.name}.`;
  return next
    ? `${done} Next: ${describeCard(next)}.`
    : `${done} That's the end of this deck.`;
}

/** What a screen reader is told when a swipe is undone (ADR-0006 rule 9). */
export function undoMessage(card: RecipeCard, direction: Direction): string {
  const choice = direction === "right" ? "save" : "skip";
  return `Undid the ${choice} of ${card.name}. It's back on top.`;
}
