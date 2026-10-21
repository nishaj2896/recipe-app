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
