import { artFor } from "./registry";
import { soupFor } from "./soup";
import sprite from "./sprite.svg?raw";

interface Props {
  ingredientId: string;
  categoryId: string;
  size?: number;
  className?: string;
}

/** One ingredient's drawing. Decorative: the name next to it is the label. */
export function IngredientArt({ ingredientId, categoryId, size = 56, className }: Props) {
  const art = artFor(ingredientId, categoryId);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      aria-hidden="true"
      className={className}
      data-art={art}
    >
      <use href={`#art-${art}`} />
    </svg>
  );
}

/** The pantry jar the ingredients fly into. */
export function JarArt({ size = 64 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <use href="#art-jar" />
    </svg>
  );
}

/**
 * Puts every drawing on the page once, so each icon is a cheap <use>. It must
 * not be display:none: browsers then skip the gradients the symbols use.
 * The markup is our own build-time file, never user data.
 */
export function ArtSprite() {
  return (
    <div
      aria-hidden="true"
      style={{ position: "absolute", width: 0, height: 0, overflow: "hidden" }}
      dangerouslySetInnerHTML={{ __html: sprite }}
    />
  );
}

/**
 * A drawn dish for a recipe: the data has no photos, so a bowl in the
 * recipe's own colour stands in for one.
 */
export function DishArt({ recipeId, size = 200 }: { recipeId: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size * 0.7}
      viewBox="0 0 100 70"
      aria-hidden="true"
      style={{ color: soupFor(recipeId) }}
    >
      <use href="#art-bowl" />
    </svg>
  );
}

/** The cooking pot and its lid, drawn apart so the lid can rattle. */
export function PotArt({ size = 160 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <use href="#art-pot" />
    </svg>
  );
}

export function LidArt({ size = 160 }: { size?: number }) {
  return (
    <svg width={size} height={size * 0.4} viewBox="0 0 100 40" aria-hidden="true">
      <use href="#art-lid" />
    </svg>
  );
}
