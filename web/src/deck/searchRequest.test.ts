import { emptyDevice, MAX_HIDDEN } from "../store/device";
import { MAX_INGREDIENTS, searchFor } from "./searchRequest";

const ids = (count: number, prefix: string) =>
  Array.from({ length: count }, (_, index) => `${prefix}-${String(index)}`);

test("an empty pantry has nothing to search for", () => {
  expect(searchFor(emptyDevice)).toBeNull();
});

test("past the API's limits the newest ingredients and skips are sent", () => {
  const search = searchFor({
    ...emptyDevice,
    pantry: ids(MAX_INGREDIENTS + 5, "ingredient"),
    hidden: ids(MAX_HIDDEN, "recipe"),
  });

  expect(search?.ingredient_ids).toHaveLength(MAX_INGREDIENTS);
  expect(search?.ingredient_ids[0]).toBe("ingredient-5");
  expect(search?.hidden_recipe_ids).toHaveLength(MAX_HIDDEN);
});

test("the deck's filters go with the search", () => {
  const search = searchFor({
    ...emptyDevice,
    pantry: ["paneer"],
    diet: "vegetarian",
    maxTotalMinutes: 30,
  });

  expect(search).toMatchObject({ diet: "vegetarian", max_total_minutes: 30 });
});
