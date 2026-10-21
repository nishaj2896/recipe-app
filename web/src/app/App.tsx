import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LazyMotion, MotionConfig } from "motion/react";
import { Suspense, useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { ArtSprite } from "../art/IngredientArt";
import { FlightProvider } from "../motion/flight";
import { PantryScreen } from "../pantry/PantryScreen";
import { ScreenError } from "./ScreenError";
import { CookbookScreen, DeckScreen, preloadScreens, RecipeScreen } from "./screens";

// If the features can't be fetched, the app still works, only without
// animation: the failure is reported and the loader never settles, so motion
// keeps rendering plain elements. (Retrying in place doesn't help: the
// browser remembers a module that failed to load until the page reloads.)
const loadMotionFeatures = () =>
  import("./motionFeatures")
    .then((module) => module.default)
    .catch((error: unknown) => {
      console.warn("Animations are off: their code didn't load.", error);
      return new Promise<never>(() => undefined);
    });

export function App() {
  // One client per mount, so tests never share a cache.
  const [queryClient] = useState(() => new QueryClient());
  useEffect(preloadScreens, []);
  return (
    <QueryClientProvider client={queryClient}>
      {/* "user" follows the phone's reduce-motion setting (ADR-0006 rule 7). */}
      <MotionConfig reducedMotion="user">
        {/* `m` components get their features from a chunk loaded after the
            first screen, which keeps the main bundle small (issue #52). */}
        <LazyMotion features={loadMotionFeatures} strict>
          <ArtSprite />
          <FlightProvider>
            <BrowserRouter>
              {/* A screen's code is almost always preloaded by the time it's
                  opened, so the wait, if any, shows the page background. If
                  it can't be fetched, ScreenError offers a reload. */}
              <ScreenError>
                <Suspense fallback={null}>
                  <Routes>
                    <Route path="/" element={<PantryScreen />} />
                    <Route path="/deck" element={<DeckScreen />} />
                    <Route path="/saved" element={<CookbookScreen />} />
                    <Route path="/recipe/:recipeId" element={<RecipeScreen />} />
                  </Routes>
                </Suspense>
              </ScreenError>
            </BrowserRouter>
          </FlightProvider>
        </LazyMotion>
      </MotionConfig>
    </QueryClientProvider>
  );
}
