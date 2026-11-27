import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

/**
 * The API lives on the same origin under /api (ADR-0006 rule 3). `fetch` is
 * looked up on every call, so tests can stub the global.
 */
export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  fetch: (request) => globalThis.fetch(request),
});

/**
 * An API call that failed with an HTTP status. Queries throw it, so the
 * QueryClient can tell a 503 (the server asking clients to back off,
 * ADR-0013 rule 1) from a dropped connection.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/**
 * Whether a failed query may try again by itself: up to three times, as
 * TanStack Query does by default, but never after a 503. The server said
 * "not now"; the screen's own Try again is the person's call.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status === 503) return false;
  return failureCount < 3;
}

export type RecipeCard = components["schemas"]["RecipeCard"];
export type CatalogIngredient = components["schemas"]["CatalogIngredient"];
export type StapleKindGroup = components["schemas"]["StapleKindGroup"];
export type IngredientRef = components["schemas"]["IngredientRef"];
export type RecipeIngredient = components["schemas"]["RecipeIngredient"];
export type PairCard = components["schemas"]["PairCard"];
export type FoundRecipe = components["schemas"]["FoundRecipe"];
