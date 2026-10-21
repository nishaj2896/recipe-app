import { swipeOutcome } from "./swipe";

const WIDTH = 400;

test.each([
  ["a short drag springs back", 60, 0, null],
  ["a drag past 35% saves", 141, 0, "right"],
  ["a drag past 35% to the left skips", -141, 0, "left"],
  ["a quick flick commits however short", 40, 900, "right"],
  ["a flick against the drag cancels", 160, -900, null],
  ["a tap that never moved does nothing", 0, 0, null],
] as const)("%s", (_case, offset, velocity, expected) => {
  expect(swipeOutcome(offset, velocity, WIDTH)).toBe(expected);
});
