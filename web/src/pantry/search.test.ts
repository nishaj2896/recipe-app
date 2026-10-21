import { CATALOG } from "../test/api";
import { searchIngredients } from "./search";

const names = (text: string) => searchIngredients(CATALOG, text).map((item) => item.name);

test("an empty query matches nothing", () => {
  expect(names("  ")).toEqual([]);
});

test("the start of the name beats the start of a later word", () => {
  expect(names("pot")).toEqual(["Potato", "Sweet potato"]);
});

test("other names for an ingredient find it", () => {
  expect(names("aubergine")).toEqual(["Brinjal"]);
});

test("matching ignores case and accents", () => {
  expect(names("PANÉER")).toEqual(["Paneer"]);
});

test("results are capped", () => {
  expect(searchIngredients(CATALOG, "a", 2)).toHaveLength(2);
});
