import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

/** The API lives on the same origin under /api (ADR-0006 rule 3). */
export const api = createClient<paths>({ baseUrl: "/" });

export type RecipeCard = components["schemas"]["RecipeCard"];
export type CatalogIngredient = components["schemas"]["CatalogIngredient"];
