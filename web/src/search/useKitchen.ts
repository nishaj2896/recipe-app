import { useMemo } from "react";

import { useStaples } from "../api/queries";
import type { FoodRules } from "../rules/check";
import { useDevice } from "../store/device";
import { haveCount } from "./haveCount";

/** What a search row compares a recipe with: the food rules and the kitchen. */
export function useKitchen(): {
  rules: FoodRules;
  have: (ingredientIds: readonly string[]) => number;
} {
  const diet = useDevice((state) => state.diet);
  const jain = useDevice((state) => state.jain);
  const avoidAllergens = useDevice((state) => state.avoidAllergens);
  const avoidIngredients = useDevice((state) => state.avoidIngredients);
  const pantry = useDevice((state) => state.pantry);
  const outOfStaples = useDevice((state) => state.outOfStaples);
  const staples = useStaples();
  const stapleIds = useMemo(
    () =>
      new Set(
        (staples.data ?? []).flatMap((group) =>
          group.categories.flatMap((category) => category.staples.map((item) => item.id)),
        ),
      ),
    [staples.data],
  );
  const have = useMemo(() => {
    const inPantry = new Set(pantry);
    const out = new Set(outOfStaples);
    return (ids: readonly string[]) => haveCount(ids, inPantry, stapleIds, out);
  }, [pantry, outOfStaples, stapleIds]);
  return { rules: { diet, jain, avoidAllergens, avoidIngredients }, have };
}
