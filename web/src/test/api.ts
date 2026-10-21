import { vi } from "vitest";

import type { CatalogIngredient, StapleKindGroup } from "../api/client";

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

/** Answers the API's catalog routes from the fixtures above. */
export function stubApi(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      const body =
        path === "/api/v1/ingredients"
          ? { ingredients: CATALOG }
          : path === "/api/v1/staples"
            ? { groups: STAPLES }
            : null;
      return Promise.resolve(
        body
          ? Response.json(body)
          : new Response(null, { status: 404, statusText: "Not Found" }),
      );
    }),
  );
}
