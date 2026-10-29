import { describe, expect, it } from "vitest";

import { scaledAmount, type Unit } from "./scale";

const at = (amount: number, unit: Unit, serves: number, servings: number) =>
  scaledAmount(amount, unit, serves, servings);

describe("scaledAmount", () => {
  it("shows a written amount unchanged at the written servings", () => {
    expect(at(250, "g", 4, 4)).toBe("250 g");
    expect(at(0.5, "kg", 4, 4)).toBe("0.5 kg");
    expect(at(0.333, "tsp", 4, 4)).toBe("⅓ tsp");
    expect(at(0.667, "cup", 4, 4)).toBe("⅔ cup");
    expect(at(1.5, "tbsp", 4, 4)).toBe("1½ tbsp");
    expect(at(0.5, "medium", 4, 4)).toBe("½ medium");
    expect(at(1, "small-head", 4, 4)).toBe("1 small head");
    expect(at(3, "clove", 4, 4)).toBe("3 cloves");
    expect(at(1, "pinch", 2, 2)).toBe("1 pinch");
  });

  it("rounds grams and millilitres to fives under 100 and tens from 100", () => {
    expect(at(30, "g", 4, 3)).toBe("25 g"); // 22.5 is halfway, so up
    expect(at(30, "g", 4, 1)).toBe("10 g"); // 7.5 is halfway, so up
    expect(at(250, "ml", 4, 3)).toBe("190 ml"); // 187.5
    expect(at(40, "g", 4, 10)).toBe("100 g");
    expect(at(130, "g", 4, 3)).toBe("100 g"); // 97.5 rounds to 100 on the grid of five
  });

  it("switches to kg and l from 1,000", () => {
    expect(at(600, "g", 4, 12)).toBe("1.8 kg");
    expect(at(250, "ml", 2, 12)).toBe("1.5 l");
    expect(at(500, "g", 4, 8)).toBe("1 kg");
    expect(at(330, "ml", 4, 3)).toBe("250 ml"); // 247.5, so it stays in ml
  });

  it("keeps kg and l in steps of 0.05", () => {
    expect(at(1, "kg", 4, 3)).toBe("0.75 kg");
    expect(at(0.5, "l", 4, 1)).toBe("0.15 l"); // 0.125 is halfway, so up
  });

  it("picks the nearer of quarters and thirds for spoons and cups", () => {
    expect(at(1, "tsp", 4, 2)).toBe("½ tsp");
    expect(at(1, "tsp", 4, 3)).toBe("¾ tsp");
    expect(at(2, "tbsp", 6, 1)).toBe("⅓ tbsp");
    expect(at(1, "cup", 3, 5)).toBe("1⅔ cups");
    expect(at(1, "cup", 4, 8)).toBe("2 cups");
  });

  it("sends a spoon tie between a quarter and a third to the larger", () => {
    // 7/24 sits exactly between ¼ and ⅓.
    expect(at(7, "tsp", 24, 1)).toBe("⅓ tsp");
  });

  it("never rounds below one grid step", () => {
    expect(at(0.25, "tsp", 4, 1)).toBe("¼ tsp");
    expect(at(5, "g", 4, 1)).toBe("5 g");
    expect(at(0.05, "kg", 4, 1)).toBe("0.05 kg");
    expect(at(0.5, "large", 4, 1)).toBe("½ large");
    expect(at(1, "clove", 4, 1)).toBe("1 clove");
  });

  it("rounds produce to halves and countables to whole numbers", () => {
    expect(at(1, "medium", 4, 6)).toBe("1½ medium");
    expect(at(1, "bunch", 4, 9)).toBe("2½ bunches"); // 2.25 is halfway, so up
    expect(at(1, "can", 4, 6)).toBe("2 cans"); // 1.5 is halfway, so up
    expect(at(6, "leaf", 4, 2)).toBe("3 leaves");
  });
});
