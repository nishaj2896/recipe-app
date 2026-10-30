import { render, screen } from "@testing-library/react";

import { recipe } from "../test/api";
import { RecipeFace } from "./RecipeFace";

const categories = new Map<string, string>();

test("a card with a long wait says to plan ahead", () => {
  const card = {
    ...recipe(1, "Idli", ["rice"]),
    plan_ahead: { wait_minutes: 840, note: "soak and ferment overnight" },
  };
  render(<RecipeFace card={card} categories={categories} />);

  expect(screen.getByText(/Plan ahead: soak and ferment overnight/)).toBeInTheDocument();
});

test("a card without a wait shows no plan ahead chip", () => {
  render(<RecipeFace card={recipe(1, "Idli", ["rice"])} categories={categories} />);

  expect(screen.getByText("Idli")).toBeInTheDocument();
  expect(screen.queryByText(/Plan ahead/)).toBeNull();
});
