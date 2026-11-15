import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { api } from "./client";

// The catalog changes only when the data is synced, and the browser
// revalidates with the ETag the API sends, so one fetch per visit is enough.
const ONCE_PER_VISIT = { staleTime: Infinity, gcTime: Infinity } as const;

const ingredientsQuery = {
  queryKey: ["ingredients"],
  queryFn: async () => {
    const { data, error } = await api.GET("/api/v1/ingredients");
    if (error) throw new Error("could not load the ingredients");
    return data.ingredients;
  },
  ...ONCE_PER_VISIT,
};

/** Every live ingredient, staples included: anything can be avoided. */
export function useIngredients() {
  return useQuery(ingredientsQuery);
}

/** Ingredients the user can pick: everything but staples, which are assumed. */
export function useCatalog() {
  return useQuery({
    ...ingredientsQuery,
    select: (ingredients) => ingredients.filter((item) => item.class !== "S"),
  });
}

export function useStaples() {
  return useQuery({
    queryKey: ["staples"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/staples");
      if (error) throw new Error("could not load the staples");
      return data.groups;
    },
    ...ONCE_PER_VISIT,
  });
}

/**
 * One recipe's details, or null when the API says it doesn't exist right now.
 * A 404 can be temporary (ADR-0005, Risk), so the saved id is kept and the
 * recipe shows as unavailable (ADR-0006 rule 5).
 */
export function recipeQuery(id: string) {
  return {
    queryKey: ["recipe", id],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/api/v1/recipes/{recipe_id}", {
        params: { path: { recipe_id: id } },
      });
      if (data) return data;
      if (response.status === 404) return null;
      throw new Error(`could not load recipe ${id}: ${error.title}`);
    },
    // A recipe never changes within a visit.
    staleTime: Infinity,
  };
}

export function useRecipe(id: string) {
  return useQuery(recipeQuery(id));
}

/** The most results one search page holds, and the deepest "See all" goes. */
export const SEARCH_PAGE = 20;
/** Recipe matches under the pantry's search box. */
export const DEFAULT_RESULTS = 5;
export const MAX_SEARCH_OFFSET = 200;

/**
 * Recipes matching typed text (ADR-0012 rule 10), `limit` at a time from
 * `offset`. Only for 2 to 60 characters, which the API accepts.
 */
async function findRecipes(text: string, limit: number, offset: number) {
  const { data, error } = await api.GET("/api/v1/recipes", {
    params: { query: { q: text, limit, offset } },
  });
  if (error) throw new Error(`could not search recipes: ${error.title}`);
  // The text rides along: while the next search loads, the last results
  // still show, and must be described by the text they answer.
  return { ...data, q: text };
}

/** Whether typed text is long enough to search recipes for. */
export const searchable = (text: string) => text.trim().length >= 2;

/** The first few matches, for the results under the search box. */
export function useRecipeSearch(text: string, limit: number) {
  const q = text.trim().slice(0, 60);
  return useQuery({
    queryKey: ["find", q, limit],
    queryFn: () => findRecipes(q, limit, 0),
    enabled: searchable(q),
    // The API caches for five minutes; so can the app.
    staleTime: 5 * 60_000,
    placeholderData: (previous) => previous,
  });
}

/** Every match, a page at a time, for "See all" (rule 11). */
export function useAllRecipeResults(text: string) {
  const q = text.trim().slice(0, 60);
  return useInfiniteQuery({
    queryKey: ["find-all", q],
    queryFn: ({ pageParam }) => findRecipes(q, SEARCH_PAGE, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const next = pages.length * SEARCH_PAGE;
      return next < last.total && next <= MAX_SEARCH_OFFSET ? next : undefined;
    },
    enabled: searchable(q),
    staleTime: 5 * 60_000,
    // The last results stay while the next search loads, so the list doesn't blink.
    placeholderData: (previous) => previous,
  });
}
