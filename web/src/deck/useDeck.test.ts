import { expect, test } from "vitest";

import { retryAfterSeconds } from "./useDeck";

test.each([
  ["2", 2],
  [" 5 ", 5],
  ["0", 1],
  ["3600", 30],
  [null, 2],
  ["Wed, 21 Oct 2026 07:28:00 GMT", 2],
  ["-3", 2],
  ["1.5", 2],
])("Retry-After %j waits %i s", (header, seconds) => {
  expect(retryAfterSeconds(header)).toBe(seconds);
});
