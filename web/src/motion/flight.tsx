import { animate } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { IngredientArt } from "../art/IngredientArt";
import { FlightContext } from "./flightContext";
import { haptic } from "./haptics";
import { usePrefersReducedMotion } from "./reducedMotion";

const ART_SIZE = 64;

interface Point {
  x: number;
  y: number;
}

interface Flight {
  key: number;
  ingredientId: string;
  categoryId: string;
  from: Point;
  to: Point;
}

function transformAt(flight: Flight, progress: number): string {
  const { from, to } = flight;
  // The arc rises higher the further the drawing has to travel.
  const height = 90 + 0.2 * Math.hypot(to.x - from.x, to.y - from.y);
  const x = from.x + (to.x - from.x) * progress;
  const y = from.y + (to.y - from.y) * progress - 4 * height * progress * (1 - progress);
  const scale = 1.15 - 0.7 * progress;
  const rotate = -8 - 192 * progress;
  return `translate(${x}px, ${y}px) scale(${scale}) rotate(${rotate}deg)`;
}

/**
 * One drawing in the air. A single spring drives its progress from the tile
 * to the jar, and the path is a parabola over that progress, so the drawing
 * is thrown up and falls in. Only `transform` changes (ADR-0006 rule 7).
 */
function FlightArt({
  flight,
  onLand,
}: {
  flight: Flight;
  onLand: (key: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let landed = false;
    const controls = animate(0, 1, {
      type: "spring",
      stiffness: 120,
      damping: 19,
      restDelta: 0.002,
      onUpdate: (progress) => {
        element.style.transform = transformAt(flight, progress);
        // It has reached the jar; don't wait for the spring to settle.
        if (progress >= 0.98 && !landed) {
          landed = true;
          onLand(flight.key);
        }
      },
    });
    void controls.then(() => {
      if (!landed) onLand(flight.key);
    });
    return () => {
      controls.stop();
    };
  }, [flight, onLand]);

  return (
    <div
      ref={ref}
      data-testid="flight"
      style={{ position: "absolute", left: 0, top: 0, transform: transformAt(flight, 0) }}
    >
      <IngredientArt
        ingredientId={flight.ingredientId}
        categoryId={flight.categoryId}
        size={ART_SIZE}
      />
    </div>
  );
}

function centre(element: Element): Point {
  const box = element.getBoundingClientRect();
  return {
    x: box.left + box.width / 2 - ART_SIZE / 2,
    y: box.top + box.height / 2 - ART_SIZE / 2,
  };
}

/**
 * The ingredient flight (ADR-0006 rule 7: things move to where they live).
 * Each tap gets its own flight, so the user can keep tapping while earlier
 * ones are still in the air.
 */
export function FlightProvider({ children }: { children: ReactNode }) {
  const reduceMotion = usePrefersReducedMotion();
  const jarRef = useRef<HTMLButtonElement | null>(null);
  const nextKey = useRef(0);
  const [flights, setFlights] = useState<Flight[]>([]);
  const [landings, setLandings] = useState(0);

  const land = useCallback((key: number) => {
    setFlights((current) => current.filter((flight) => flight.key !== key));
    setLandings((count) => count + 1);
    haptic.land();
  }, []);

  const launch = useCallback(
    (origin: Element, ingredientId: string, categoryId: string) => {
      const jar = jarRef.current;
      // With reduced motion nothing flies: the jar just acknowledges the add.
      if (reduceMotion || !jar) {
        setLandings((count) => count + 1);
        return;
      }
      const key = nextKey.current++;
      setFlights((current) => [
        ...current,
        { key, ingredientId, categoryId, from: centre(origin), to: centre(jar) },
      ]);
    },
    [reduceMotion],
  );

  const api = useMemo(() => ({ launch, jarRef, landings }), [launch, landings]);

  return (
    <FlightContext.Provider value={api}>
      {children}
      <div
        aria-hidden="true"
        style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 50 }}
      >
        {flights.map((flight) => (
          <FlightArt key={flight.key} flight={flight} onLand={land} />
        ))}
      </div>
    </FlightContext.Provider>
  );
}
