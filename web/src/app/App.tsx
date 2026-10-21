import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { PantryScreen } from "../screens/PantryScreen";

export function App() {
  // One client per mount, so tests never share a cache.
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<PantryScreen />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
