import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { domAnimation, LazyMotion, MotionConfig } from "motion/react";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { ArtSprite } from "../art/IngredientArt";
import { DeckScreen } from "../deck/DeckScreen";
import { FlightProvider } from "../motion/flight";
import { PantryScreen } from "../pantry/PantryScreen";

export function App() {
  // One client per mount, so tests never share a cache.
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      {/* "user" follows the phone's reduce-motion setting (ADR-0006 rule 7). */}
      <MotionConfig reducedMotion="user">
        {/* Only the DOM animation features, with `m` components, keep the bundle small. */}
        <LazyMotion features={domAnimation} strict>
          <ArtSprite />
          <FlightProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<PantryScreen />} />
                <Route path="/deck" element={<DeckScreen />} />
              </Routes>
            </BrowserRouter>
          </FlightProvider>
        </LazyMotion>
      </MotionConfig>
    </QueryClientProvider>
  );
}
