import { describe, expect, it } from "vitest";

import { formatWait } from "./wait";

describe("formatWait", () => {
  it("shows hours, with minutes under a day", () => {
    expect(formatWait(60)).toBe("1 h");
    expect(formatWait(90)).toBe("1 h 30 min");
    expect(formatWait(480)).toBe("8 h");
  });

  it("shows days, with hours but not minutes", () => {
    expect(formatWait(24 * 60)).toBe("1 day");
    expect(formatWait(36 * 60)).toBe("1 day 12 h");
    expect(formatWait(3 * 24 * 60 + 30)).toBe("3 days");
    expect(formatWait(7 * 24 * 60)).toBe("7 days");
  });
});
