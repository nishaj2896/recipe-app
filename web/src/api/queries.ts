import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

// The catalog changes only when the data is synced, and the browser
// revalidates with the ETag the API sends, so one fetch per visit is enough.
const ONCE_PER_VISIT = { staleTime: Infinity, gcTime: Infinity } as const;

/** Ingredients the user can pick: everything but staples, which are assumed. */
export function useCatalog() {
  return useQuery({
    queryKey: ["ingredients"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/ingredients");
      if (error) throw new Error("could not load the ingredients");
      return data.ingredients.filter((item) => item.class !== "S");
    },
    ...ONCE_PER_VISIT,
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
