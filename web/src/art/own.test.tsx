import { render, screen } from "@testing-library/react";

import { IngredientArt } from "./IngredientArt";
import ownArt from "./own.json";

const files = import.meta.glob<string>("/public/art/ingredients/*.svg", {
  query: "?raw",
  import: "default",
  eager: true,
});

test("every ingredient listed as drawn has its own standalone file", () => {
  const missing = ownArt.filter((id) => {
    const markup = files[`/public/art/ingredients/${id}.svg`];
    return !markup?.startsWith("<svg") || !markup.includes('viewBox="0 0 100 100"');
  });
  expect(missing).toEqual([]);
});

test("no drawing file is left out of the list", () => {
  const listed = new Set(ownArt);
  const stray = Object.keys(files)
    .map((path) => path.replace(/^.*\/(.+)\.svg$/, "$1"))
    .filter((id) => !listed.has(id));
  expect(stray).toEqual([]);
});

test("an ingredient drawn as itself shows its own drawing", () => {
  render(
    <span data-testid="art">
      <IngredientArt ingredientId="masoor-dal" categoryId="dals-and-pulses" />
    </span>,
  );
  const img = screen.getByTestId("art").querySelector("img");
  expect(img).toHaveAttribute("src", "/art/ingredients/masoor-dal.svg");
  expect(img).toHaveAttribute("alt", "");
});

test("an ingredient without its own drawing keeps the category icon", () => {
  render(
    <span data-testid="art">
      <IngredientArt ingredientId="no-such-thing" categoryId="dals-and-pulses" />
    </span>,
  );
  expect(screen.getByTestId("art").querySelector("svg")).toHaveAttribute(
    "data-art",
    "art-lentils",
  );
});
