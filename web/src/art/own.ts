import ownArt from "./own.json";

/** Ingredients drawn as themselves, each in its own file under public/art. */
const OWN_ART: ReadonlySet<string> = new Set(ownArt);

/** Where an ingredient's own drawing lives, or undefined if it has none. */
export function ownArtUrl(ingredientId: string): string | undefined {
  return OWN_ART.has(ingredientId)
    ? `${import.meta.env.BASE_URL}art/ingredients/${ingredientId}.svg`
    : undefined;
}
