import { filterSummary } from "./filters";

test.each([
  [null, null, "Any diet · Any time"],
  ["vegetarian", 30, "Veg · ≤30 min"],
  ["egg", null, "Veg + egg · Any time"],
  ["vegan", 15, "Vegan · ≤15 min"],
] as const)("%s and %s read as %s", (diet, minutes, text) => {
  expect(filterSummary(diet, minutes)).toBe(text);
});
