import { render, screen } from "@testing-library/react";

import { App } from "./App";

test("the app opens on the pantry screen", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { name: "What's in your kitchen?" }),
  ).toBeInTheDocument();
});
