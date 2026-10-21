import { useInfiniteQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { MAX_HIDDEN, useDevice } from "../store/device";
import type { SearchRequest } from "./searchRequest";

/** Cursor problems the API answers with 422: the deck starts over. */
const CURSOR_PROBLEMS = new Set(["/problems/cursor-expired", "/problems/invalid-cursor"]);

export class SearchError extends Error {
  constructor(readonly cursorRefused: boolean) {
    super(cursorRefused ? "the next deck's cursor was refused" : "the search failed");
  }
}

/**
 * The decks for one search, 20 cards each, fetched one at a time. Each fetch
 * sends the hidden list as it is then, so a recipe skipped on this deck never
 * comes back on the next one; the cursor ignores the hidden list, so that's
 * allowed (ADR-0003 rule 9).
 */
export function useDeck(search: SearchRequest | null, round: number) {
  return useInfiniteQuery({
    queryKey: ["deck", search, round],
    enabled: search !== null,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      if (!search) throw new SearchError(false);
      const { data, error } = await api.POST("/api/v1/recipes/search", {
        body: {
          ...search,
          hidden_recipe_ids: useDevice.getState().hidden.slice(-MAX_HIDDEN),
          cursor: pageParam,
        },
      });
      if (data) return data;
      throw new SearchError(pageParam !== null && CURSOR_PROBLEMS.has(error.type));
    },
    getNextPageParam: (page) => page.next_cursor,
    // A deck is dealt once: refetching would reshuffle cards under the finger.
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });
}
