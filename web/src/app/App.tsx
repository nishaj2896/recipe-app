import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { domMax, LazyMotion, MotionConfig } from "motion/react";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { ArtSprite } from "../art/IngredientArt";
import { CookbookScreen } from "../cookbook/CookbookScreen";
import { DeckScreen } from "../deck/DeckScreen";
import { FlightProvider } from "../motion/flight";
import { PantryScreen } from "../pantry/PantryScreen";
import { RecipeScreen } from "../recipe/RecipeScreen";

export function App() {
  // One client per mount, so tests never share a cache.
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      {/* "user" follows the phone's reduce-motion setting (ADR-0006 rule 7). */}
      <MotionConfig reducedMotion="user">
        {/* `m` components with only the DOM features keep the bundle small;
            domMax adds the drag the swipe deck needs. */}
        <LazyMotion features={domMax} strict>
          <ArtSprite />
          <FlightProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<PantryScreen />} />
                <Route path="/deck" element={<DeckScreen />} />
                <Route path="/saved" element={<CookbookScreen />} />
                <Route path="/recipe/:recipeId" element={<RecipeScreen />} />
              </Routes>
            </BrowserRouter>
          </FlightProvider>
        </LazyMotion>
      </MotionConfig>
    </QueryClientProvider>
  );
}
