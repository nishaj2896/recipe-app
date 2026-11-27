import { expect, test } from "vitest";

import { ApiError, shouldRetry } from "./client";

test("a 503 is never retried automatically", () => {
  expect(shouldRetry(0, new ApiError("busy", 503))).toBe(false);
});

test.each([
  ["a dropped connection", new TypeError("Failed to fetch")],
  ["a 500", new ApiError("boom", 500)],
  ["a 502 from a proxy", new ApiError("bad gateway", 502)],
])("%s is retried up to three times, as before", (_, error) => {
  expect(shouldRetry(0, error)).toBe(true);
  expect(shouldRetry(2, error)).toBe(true);
  expect(shouldRetry(3, error)).toBe(false);
});
