import { DECK } from "../test/api";
import { shoppingList, shoppingText } from "./shopping";

test("the most-needed item comes first, then by name", () => {
  const list = shoppingList(DECK);
  expect(list.map((item) => [item.ingredient.name, item.recipes])).toEqual([
    ["Cream", 2],
    ["Cauliflower", 1],
  ]);
  expect(shoppingText(list)).toBe("Shopping list\n- Cream\n- Cauliflower");
});

test("saves that need nothing make an empty list", () => {
  expect(shoppingList([])).toEqual([]);
});
