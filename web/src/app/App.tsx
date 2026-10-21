import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LazyMotion, MotionConfig } from "motion/react";
import { Suspense, useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { ArtSprite } from "../art/IngredientArt";
import { FlightProvider } from "../motion/flight";
import { PantryScreen } from "../pantry/PantryScreen";
import { CookbookScreen, DeckScreen, preloadScreens, RecipeScreen } from "./screens";

const loadMotionFeatures = () =>
  import("./motionFeatures").then((module) => module.default);

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
                  opened, so the wait, if any, shows the page background. */}
              <Suspense fallback={null}>
                <Routes>
                  <Route path="/" element={<PantryScreen />} />
                  <Route path="/deck" element={<DeckScreen />} />
                  <Route path="/saved" element={<CookbookScreen />} />
                  <Route path="/recipe/:recipeId" element={<RecipeScreen />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
          </FlightProvider>
        </LazyMotion>
      </MotionConfig>
    </QueryClientProvider>
  );
}
