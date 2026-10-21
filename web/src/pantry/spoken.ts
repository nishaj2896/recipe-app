import type { CatalogIngredient } from "../api/client";

/** The longest name, in words, that a spoken phrase is checked against. */
const MAX_WORDS = 4;

function words(text: string): string[] {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

/**
 * A rough singular, applied to both sides of every comparison, so
 * "potatoes", "eggs" and "chillies" find Potato, Egg and Chilli. It only has
 * to be consistent, not correct English.
 */
function singular(word: string): string {
  if (word.length > 4 && word.endsWith("ies")) return word.slice(0, -3) + "i";
  if (word.length > 4 && word.endsWith("oes")) return word.slice(0, -2);
  if (word.length > 3 && word.endsWith("s") && !word.endsWith("ss"))
    return word.slice(0, -1);
  return word;
}

const key = (parts: readonly string[]) => parts.map(singular).join(" ");

/**
 * Finds catalog items named in a spoken sentence such as "I have potatoes,
 * milk and a dozen eggs". Every name and other name is a phrase; the
 * sentence is read left to right, taking the longest phrase that matches at
 * each word, so "sweet potato" wins over "potato". Words that name nothing
 * ("I", "have", "a dozen") are skipped.
 */
export function findSpoken<T extends Pick<CatalogIngredient, "name">>(
  items: readonly T[],
  sentence: string,
  otherNames: (item: T) => readonly string[] = () => [],
): T[] {
  // An item's own name beats another item's other name, so "mint" is Mint,
  // not Dried mint. Between two other names, catalog order decides.
  const byPhrase = new Map<string, T>();
  const claim = (item: T, name: string) => {
    const phrase = key(words(name));
    if (phrase && !byPhrase.has(phrase)) byPhrase.set(phrase, item);
  };
  for (const item of items) claim(item, item.name);
  for (const item of items) for (const name of otherNames(item)) claim(item, name);

  const said = words(sentence);
  const found = new Set<T>();
  let at = 0;
  while (at < said.length) {
    let matched = 0;
    for (let length = Math.min(MAX_WORDS, said.length - at); length > 0; length--) {
      const item = byPhrase.get(key(said.slice(at, at + length)));
      if (item) {
        found.add(item);
        matched = length;
        break;
      }
    }
    at += matched || 1;
  }
  return [...found];
}
