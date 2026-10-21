import { render, screen } from "@testing-library/react";

import { stubApi } from "../test/api";
import { App } from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("the app opens on the pantry screen", async () => {
  stubApi();
  render(<App />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/^What's for /);
  expect(await screen.findByRole("button", { name: /Potato/ })).toBeInTheDocument();
});
