import { vi } from "vitest";

import type { CatalogIngredient, RecipeCard, StapleKindGroup } from "../api/client";
import type { components } from "../api/schema";

function ingredient(
  id: string,
  name: string,
  category: [string, string],
  searchTerms: string[] = [],
): CatalogIngredient {
  return {
    id,
    name,
    class: "A",
    kind: null,
    category: { id: category[0], name: category[1] },
    diet: "vegan",
    search_terms: searchTerms,
  };
}

const VEG: [string, string] = ["vegetables", "Vegetables"];
const DAIRY: [string, string] = ["dairy-and-eggs", "Dairy & eggs"];

/** A small catalog in the API's own shape and order. */
export const CATALOG: CatalogIngredient[] = [
  ingredient("brinjal", "Brinjal", VEG, ["aubergine", "eggplant"]),
  ingredient("carrot", "Carrot", VEG),
  ingredient("potato", "Potato", VEG),
  ingredient("sweet-potato", "Sweet potato", VEG),
  ingredient("milk", "Milk", DAIRY),
  ingredient("paneer", "Paneer", DAIRY, ["cottage cheese"]),
  ingredient("egg", "Egg", DAIRY),
  { ...ingredient("salt", "Salt", ["spices-and-seasonings", "Spices"]), class: "S" },
];

export const STAPLES: StapleKindGroup[] = [
  {
    kind: "fresh",
    categories: [
      {
        id: "vegetables",
        name: "Vegetables",
        staples: [
          { id: "onion", name: "Onion" },
          { id: "tomato", name: "Tomato" },
        ],
      },
    ],
  },
  {
    kind: "pantry",
    categories: [
      {
        id: "spices-and-seasonings",
        name: "Spices",
        staples: [
          { id: "salt", name: "Salt" },
          { id: "turmeric", name: "Turmeric" },
        ],
      },
    ],
  },
];

type SearchRequest = components["schemas"]["SearchRequest"];
type SearchResponse = components["schemas"]["SearchResponse"];

const ref = (id: string) => ({ id, name: id.charAt(0).toUpperCase() + id.slice(1) });

/** A scored card; ids are UUIDs, as the API's are. */
export function recipe(
  n: number,
  name: string,
  matched: string[],
  missing: string[] = [],
): RecipeCard {
  return {
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    name,
    tier: "scored",
    match_percentage: Math.round(
      (100 * matched.length) / (matched.length + missing.length),
    ),
    matched_ingredients: matched.map(ref),
    missing_ingredients: missing.map(ref),
    assumed_staples: [ref("salt")],
    prep_minutes: 10,
    cook_minutes: 20,
    total_minutes: 30,
    diet: "vegetarian",
  };
}

export const DECK = [
  recipe(1, "Matar Paneer", ["paneer", "potato"], ["cream"]),
  recipe(2, "Aloo Gobi", ["potato"], ["cauliflower", "cream"]),
  recipe(3, "Egg Bhurji", ["egg", "milk"]),
];

export type SearchHandler = (body: SearchRequest) => SearchResponse | Response;

/** One deck: every card, no next page, nothing ignored. */
export const oneDeck: SearchHandler = (body) => ({
  results: DECK.filter((card) => !body.hidden_recipe_ids.includes(card.id)),
  next_cursor: null,
  ignored_ingredients: [],
});

/**
 * Answers the API's catalog routes from the fixtures above, and searches
 * with `search`. Every search body is kept in `searches`.
 */
export function stubApi(search: SearchHandler = oneDeck): { searches: SearchRequest[] } {
  const searches: SearchRequest[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/recipes/search") {
        const body = (await request.json()) as SearchRequest;
        searches.push(body);
        const answer = search(body);
        return answer instanceof Response ? answer : Response.json(answer);
      }
      const body =
        path === "/api/v1/ingredients"
          ? { ingredients: CATALOG }
          : path === "/api/v1/staples"
            ? { groups: STAPLES }
            : null;
      return body
        ? Response.json(body)
        : new Response(null, { status: 404, statusText: "Not Found" });
    }),
  );
  return { searches };
}
