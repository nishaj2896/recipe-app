import { artFor } from "./registry";
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
