import { createContext, useContext, type RefObject } from "react";

export interface FlightApi {
  /** Sends an ingredient's drawing from `origin` into the pantry jar. */
  launch: (origin: Element, ingredientId: string, categoryId: string) => void;
  /** The element ingredients fly into. */
  jarRef: RefObject<HTMLButtonElement | null>;
  /** Goes up by one each time something lands, so the jar can bounce. */
  landings: number;
}

export const FlightContext = createContext<FlightApi | null>(null);

export function useFlight(): FlightApi {
  const api = useContext(FlightContext);
  if (!api) throw new Error("useFlight needs a FlightProvider");
  return api;
}
