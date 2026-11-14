import { breaks, keepsRules } from "./check";

const none = { diet: null, jain: false, avoidAllergens: [], avoidIngredients: [] };
const paneer = {
  diet: "vegetarian" as const,
  jain: true,
  allergens: ["dairy" as const],
  ingredient_ids: ["paneer", "tomato"],
};

test("no rules keep every recipe", () => {
  expect(keepsRules({ ...paneer, diet: "non_veg", jain: false }, none)).toBe(true);
});

test.each([
  ["egg", "vegetarian", true],
  ["vegetarian", "vegetarian", true],
  ["vegan", "vegetarian", false],
  ["vegetarian", "egg", false],
  ["egg", "non_veg", false],
] as const)("a %s diet and a %s recipe: kept is %s", (rule, recipe, kept) => {
  expect(keepsRules({ ...paneer, diet: recipe }, { ...none, diet: rule })).toBe(kept);
});

test("Jain needs a Jain recipe", () => {
  const rules = { ...none, diet: "vegetarian" as const, jain: true };
  expect(keepsRules(paneer, rules)).toBe(true);
  expect(breaks({ ...paneer, jain: false }, rules).jain).toBe(true);
});

test("allergens and avoided ingredients are named", () => {
  expect(
    breaks(paneer, {
      ...none,
      avoidAllergens: ["peanuts", "dairy"],
      avoidIngredients: ["tomato", "onion"],
    }),
  ).toEqual({
    diet: false,
    jain: false,
    allergens: ["dairy"],
    ingredientIds: ["tomato"],
  });
});
