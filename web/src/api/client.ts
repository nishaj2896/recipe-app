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

export type RecipeCard = components["schemas"]["RecipeCard"];
export type CatalogIngredient = components["schemas"]["CatalogIngredient"];
export type StapleKindGroup = components["schemas"]["StapleKindGroup"];
export type IngredientRef = components["schemas"]["IngredientRef"];
export type RecipeIngredient = components["schemas"]["RecipeIngredient"];
