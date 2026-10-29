import type { components } from "../api/schema";

export type Unit = components["schemas"]["Unit"];

export const MIN_SERVINGS = 1;
export const MAX_SERVINGS = 12;

type Kind = "mass" | "volume" | "spoon" | "produce" | "count";

/**
 * Each unit's kind and plural, as in the API's units.py (ADR-0008 rule 2).
 * A unit added there needs its forms and grid here too; the Record type
 * makes tsc catch one missing after `npm run api:generate`.
 */
const UNITS: Record<Unit, { kind: Kind; plural: string }> = {
  g: { kind: "mass", plural: "g" },
  kg: { kind: "mass", plural: "kg" },
  ml: { kind: "volume", plural: "ml" },
  l: { kind: "volume", plural: "l" },
  tsp: { kind: "spoon", plural: "tsp" },
  tbsp: { kind: "spoon", plural: "tbsp" },
  cup: { kind: "spoon", plural: "cups" },
  small: { kind: "produce", plural: "small" },
  medium: { kind: "produce", plural: "medium" },
  large: { kind: "produce", plural: "large" },
  "small-head": { kind: "produce", plural: "small heads" },
  bunch: { kind: "produce", plural: "bunches" },
  piece: { kind: "count", plural: "pieces" },
  clove: { kind: "count", plural: "cloves" },
  sprig: { kind: "count", plural: "sprigs" },
  slice: { kind: "count", plural: "slices" },
  leaf: { kind: "count", plural: "leaves" },
  pinch: { kind: "count", plural: "pinches" },
  can: { kind: "count", plural: "cans" },
};

// Float error (0.1 × 3 is 0.30000000000000004) must not decide a halfway case.
const EPSILON = 1e-9;

/** The nearest multiple of `step`, halfway cases up, and never below `step`. */
function toGrid(value: number, step: number): number {
  return Math.max(step, Math.round(value / step + EPSILON) * step);
}

/** Quarters or thirds, whichever is nearer; a tie goes to the larger. */
function toSpoons(value: number): number {
  const quarters = toGrid(value, 1 / 4);
  const thirds = toGrid(value, 1 / 3);
  const gap = Math.abs(quarters - value) - Math.abs(thirds - value);
  if (Math.abs(gap) < EPSILON) return Math.max(quarters, thirds);
  return gap < 0 ? quarters : thirds;
}

const FRACTIONS: Record<number, string> = { 3: "¼", 4: "⅓", 6: "½", 8: "⅔", 9: "¾" };

/** 1.5 as "1½"; the value is on a grid of quarters, thirds or halves. */
function fraction(value: number): string {
  const twelfths = Math.round(value * 12);
  const whole = Math.floor(twelfths / 12);
  const rest = FRACTIONS[twelfths % 12] ?? "";
  return whole === 0 ? rest : `${String(whole)}${rest}`;
}

/** At most two decimals, no trailing zeros: 1.8, 1.25, 2. */
function decimal(value: number): string {
  return String(Math.round(value * 100) / 100);
}

/**
 * An amount written for `serves`, scaled to `servings` and shown on its
 * unit's grid (ADR-0008 rules 2 and 8): "1.8 kg", "½ tsp", "2 cloves".
 */
export function scaledAmount(
  amount: number,
  unit: Unit,
  serves: number,
  servings: number,
): string {
  const value = (amount * servings) / serves;
  const { kind } = UNITS[unit];
  let shown: number;
  let shownUnit: Unit = unit;
  let text: string;
  switch (kind) {
    case "mass":
    case "volume":
      if (unit === "kg" || unit === "l") {
        shown = toGrid(value, 0.05);
      } else {
        shown = toGrid(value, value < 100 ? 5 : 10);
        if (shown >= 1000) {
          shown /= 1000;
          shownUnit = kind === "mass" ? "kg" : "l";
        }
      }
      text = decimal(shown);
      break;
    case "spoon":
      shown = toSpoons(value);
      text = fraction(shown);
      break;
    case "produce":
      shown = toGrid(value, 1 / 2);
      text = fraction(shown);
      break;
    case "count":
      shown = toGrid(value, 1);
      text = String(shown);
      break;
  }
  const forms = UNITS[shownUnit];
  const word = shown > 1 + EPSILON ? forms.plural : shownUnit.replace("-", " ");
  return `${text} ${word}`;
}
