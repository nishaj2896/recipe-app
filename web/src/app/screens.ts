import { lazy } from "react";

// The pantry is the first screen, so it ships in the main bundle. The others
// load on their own (issue #52) and are fetched in the background once the
// first screen is up, so opening one doesn't wait on the network.
const loadDeck = () => import("../deck/DeckScreen");
const loadCookbook = () => import("../cookbook/CookbookScreen");
const loadRecipe = () => import("../recipe/RecipeScreen");
const loadFoodRules = () => import("../rules/FoodRulesScreen");
const loadMood = () => import("../rules/MoodScreen");
const loadSearch = () => import("../search/SearchScreen");

export const DeckScreen = lazy(() =>
  loadDeck().then((module) => ({ default: module.DeckScreen })),
);
export const CookbookScreen = lazy(() =>
  loadCookbook().then((module) => ({ default: module.CookbookScreen })),
);
export const RecipeScreen = lazy(() =>
  loadRecipe().then((module) => ({ default: module.RecipeScreen })),
);
export const FoodRulesScreen = lazy(() =>
  loadFoodRules().then((module) => ({ default: module.FoodRulesScreen })),
);
export const MoodScreen = lazy(() =>
  loadMood().then((module) => ({ default: module.MoodScreen })),
);
export const SearchScreen = lazy(() =>
  loadSearch().then((module) => ({ default: module.SearchScreen })),
);

/** Fetches the other screens' code while the browser is idle. */
export function preloadScreens(): void {
  const preload = () => {
    // A failed fetch is retried when the screen is opened.
    void Promise.all([
      loadDeck(),
      loadCookbook(),
      loadRecipe(),
      loadFoodRules(),
      loadMood(),
      loadSearch(),
    ]).catch(() => undefined);
  };
  if ("requestIdleCallback" in window) requestIdleCallback(preload, { timeout: 2000 });
  else setTimeout(preload, 1000);
}
