import { fireEvent, render, screen } from "@testing-library/react";

import { recipe } from "../test/api";
import { RecipeFace } from "./RecipeFace";

const categories = new Map<string, string>();
const BOWL = 'use[href="#art-bowl"]';

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

const photo = {
  url: "/dishes/x.webp?v=0123456789ab",
  alt: "Idli on a plate",
};

test("a card with a photo shows it in place of the drawn bowl, under the garnish", () => {
  const card = { ...recipe(1, "Idli", ["rice"]), image: photo };
  render(<RecipeFace card={card} categories={categories} />);

  const image = screen.getByRole("img", { name: "Idli on a plate" });
  expect(image).toHaveAttribute("src", photo.url);
  expect(image).toHaveAttribute("draggable", "false");
  expect(document.querySelector(BOWL)).toBeNull();
  expect(screen.getByRole("img", { name: /% match/ })).toBeInTheDocument();
});

test("the drawn bowl stands in when a card's photo doesn't load", () => {
  const card = { ...recipe(1, "Idli", ["rice"]), image: photo };
  render(<RecipeFace card={card} categories={categories} />);

  fireEvent.error(screen.getByRole("img", { name: "Idli on a plate" }));

  expect(screen.queryByRole("img", { name: "Idli on a plate" })).toBeNull();
  expect(document.querySelector(BOWL)).not.toBeNull();
});

test("a card without a photo keeps the drawn bowl", () => {
  render(<RecipeFace card={recipe(1, "Idli", ["rice"])} categories={categories} />);

  expect(screen.queryByRole("img", { name: "Idli on a plate" })).toBeNull();
  expect(document.querySelector(BOWL)).not.toBeNull();
});
