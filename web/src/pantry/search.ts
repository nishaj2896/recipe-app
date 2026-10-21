import type { CatalogIngredient } from "../api/client";

function normalise(text: string): string {
  return text.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").trim();
}

/** 0 is the best match, Infinity is no match. */
function rank(item: CatalogIngredient, query: string): number {
  const name = normalise(item.name);
  if (name === query) return 0;
  if (name.startsWith(query)) return 1;
  if (name.split(/[\s-]+/).some((word) => word.startsWith(query))) return 2;
  if (item.search_terms.some((term) => normalise(term).includes(query))) return 3;
  if (name.includes(query)) return 4;
  return Infinity;
}

/**
 * Ingredients matching what the user typed, best first: whole name, then the
 * start of the name, then the start of any word, then other names for it
 * ("aubergine" finds brinjal). Ties keep the catalog's order.
 */
export function searchIngredients(
  catalog: readonly CatalogIngredient[],
  text: string,
  limit = 30,
): CatalogIngredient[] {
  const query = normalise(text);
  if (!query) return [];
  return catalog
    .map((item, index) => ({ item, index, score: rank(item, query) }))
    .filter(({ score }) => score !== Infinity)
    .sort((a, b) => a.score - b.score || a.index - b.index)
    .slice(0, limit)
    .map(({ item }) => item);
}
