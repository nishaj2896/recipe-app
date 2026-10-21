import { DECK } from "../test/api";
import { describeCard, swipeMessage, undoMessage } from "./announce";

const [matar, aloo] = DECK as [(typeof DECK)[0], (typeof DECK)[0]];

test("a card is described by its name, match and what's missing", () => {
  expect(describeCard(aloo)).toMatch(
    /^Aloo Gobi, \d+% match, missing cauliflower, cream$/,
  );
  expect(describeCard({ ...aloo, match_percentage: null })).toContain("pantry basics");
  expect(describeCard({ ...aloo, missing_ingredients: [] })).toContain("nothing missing");
});

test("a swipe names the choice and the next card, or the deck's end", () => {
  expect(swipeMessage(matar, "right", aloo)).toBe(
    `Saved Matar Paneer. Next: ${describeCard(aloo)}.`,
  );
  expect(swipeMessage(matar, "left", undefined)).toBe(
    "Skipped Matar Paneer. That's the end of this deck.",
  );
});

test("an undo names what was undone", () => {
  expect(undoMessage(matar, "right")).toBe(
    "Undid the save of Matar Paneer. It's back on top.",
  );
  expect(undoMessage(matar, "left")).toBe(
    "Undid the skip of Matar Paneer. It's back on top.",
  );
});
