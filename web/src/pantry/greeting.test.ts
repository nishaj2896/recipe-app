import { greetingFor } from "./greeting";

test.each([
  [7, "Good morning", "breakfast"],
  [13, "Good afternoon", "lunch"],
  [19, "Good evening", "dinner"],
  [2, "Up late", "a midnight snack"],
])("at %i:00 it says %s and asks about %s", (hour, hello, meal) => {
  expect(greetingFor(new Date(2026, 9, 21, hour))).toEqual({ hello, meal });
});
