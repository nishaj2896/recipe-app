import { artFor, CATEGORY_ART, DEFAULT_ART, INGREDIENT_ART } from "./registry";
import sprite from "./sprite.svg?raw";

const symbols = new Set(
  [...sprite.matchAll(/<symbol id="art-([\w-]+)"/g)].map((m) => m[1]),
);

test("an ingredient with its own icon uses it", () => {
  expect(artFor("milk", "dairy-and-eggs")).toBe("milk");
});

test("any other ingredient falls back to its category's icon", () => {
  expect(artFor("goat-cheese", "dairy-and-eggs")).toBe("milk");
  expect(artFor("prawns", "fish-and-seafood")).toBe("fish");
});

test("an unknown category still gets a drawing", () => {
  expect(artFor("dragon-fruit", "a-category-from-the-future")).toBe(DEFAULT_ART);
});

test("every icon the registry names is drawn in the sprite", () => {
  const named = new Set([
    ...Object.values(INGREDIENT_ART),
    ...Object.values(CATEGORY_ART),
    DEFAULT_ART,
  ]);
  expect([...named].filter((art) => !symbols.has(art))).toEqual([]);
});
