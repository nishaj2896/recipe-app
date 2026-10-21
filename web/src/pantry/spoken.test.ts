import { CATALOG } from "../test/api";
import { findSpoken } from "./spoken";

const names = (sentence: string) =>
  findSpoken(CATALOG, sentence, (item) => item.search_terms).map((item) => item.id);

test("finds each ingredient named in a sentence, in the order said", () => {
  expect(names("I have potatoes, milk and a dozen eggs")).toEqual([
    "potato",
    "milk",
    "egg",
  ]);
});

test("the longest name wins, so sweet potato isn't heard as potato", () => {
  expect(names("sweet potatoes and carrots")).toEqual(["sweet-potato", "carrot"]);
});

test("other names count, and a repeat is found once", () => {
  expect(names("aubergine, cottage cheese and more aubergines")).toEqual([
    "brinjal",
    "paneer",
  ]);
});

test("capitals and accents don't matter", () => {
  expect(names("PANEER and Pötato")).toEqual(["paneer", "potato"]);
});

test("a sentence naming nothing finds nothing", () => {
  expect(names("what can I cook tonight")).toEqual([]);
  expect(names("")).toEqual([]);
});

test("an ingredient's own name beats another's other name, whatever the order", () => {
  const herbs = [
    { name: "Dried mint", other: ["mint"] },
    { name: "Mint", other: ["fresh mint"] },
  ];
  expect(findSpoken(herbs, "some mint", (item) => item.other)).toEqual([herbs[1]]);
});
