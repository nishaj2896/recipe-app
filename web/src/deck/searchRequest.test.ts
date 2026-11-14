import { emptyDevice, MAX_HIDDEN, noMood } from "../store/device";
import { MAX_AVOIDED_INGREDIENTS, MAX_INGREDIENTS, searchFor } from "./searchRequest";

const ids = (count: number, prefix: string) =>
  Array.from({ length: count }, (_, index) => `${prefix}-${String(index)}`);

test("an empty pantry has nothing to search for", () => {
  expect(searchFor(emptyDevice, noMood)).toBeNull();
});

test("past the API's limits the newest ingredients, skips and avoids are sent", () => {
  const search = searchFor(
    {
      ...emptyDevice,
      pantry: ids(MAX_INGREDIENTS + 5, "ingredient"),
      hidden: ids(MAX_HIDDEN, "recipe"),
      avoidIngredients: ids(MAX_AVOIDED_INGREDIENTS + 1, "avoid"),
    },
    noMood,
  );

  expect(search?.ingredient_ids).toHaveLength(MAX_INGREDIENTS);
  expect(search?.ingredient_ids[0]).toBe("ingredient-5");
  expect(search?.hidden_recipe_ids).toHaveLength(MAX_HIDDEN);
  expect(search?.avoid_ingredient_ids).toHaveLength(MAX_AVOIDED_INGREDIENTS);
  expect(search?.avoid_ingredient_ids[0]).toBe("avoid-1");
});

test("the food rules and the mood picks go with the search", () => {
  const search = searchFor(
    {
      ...emptyDevice,
      pantry: ["paneer"],
      diet: "vegetarian",
      jain: true,
      avoidAllergens: ["peanuts"],
      avoidIngredients: ["coconut"],
    },
    { courses: ["mains"], time: "30", moods: ["spicy"], weather: ["warming"] },
  );

  expect(search).toMatchObject({
    diet: "vegetarian",
    jain: true,
    avoid_allergens: ["peanuts"],
    avoid_ingredient_ids: ["coconut"],
    min_total_minutes: null,
    max_total_minutes: 30,
    courses: ["mains"],
    moods: ["spicy"],
    weather: ["warming"],
  });
});

test.each([
  ["any", null, null],
  ["15", null, 15],
  ["60", null, 60],
  ["over-60", 61, null],
] as const)("the time choice %s sends min %s and max %s", (time, min, max) => {
  const search = searchFor({ ...emptyDevice, pantry: ["paneer"] }, { ...noMood, time });

  expect(search).toMatchObject({ min_total_minutes: min, max_total_minutes: max });
});
