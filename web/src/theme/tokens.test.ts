import tokensCss from "./tokens.css?raw";

type Theme = Record<string, string>;

function parseTheme(block: string): Theme {
  const theme: Theme = {};
  for (const [, name, value] of block.matchAll(
    /(--[\w-]+):\s*(#[0-9a-f]{6}|rgba\([^)]*\));/gi,
  )) {
    if (name && value) theme[name] = value.toLowerCase();
  }
  return theme;
}

/** A translucent colour as it looks laid over an opaque one, as hex. */
function over(rgba: string, hex: string): string {
  const [r = 0, g = 0, b = 0, alpha = 1] = (rgba.match(/[\d.]+/g) ?? []).map(Number);
  const under = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return (
    "#" +
    [r, g, b]
      .map((channel, i) => Math.round(channel * alpha + (under[i] ?? 0) * (1 - alpha)))
      .map((channel) => channel.toString(16).padStart(2, "0"))
      .join("")
  );
}

const [darkBlock = "", lightBlock = ""] = tokensCss.split(
  "@media (prefers-color-scheme: light)",
);
const dark = parseTheme(darkBlock);
// The light theme only overrides colours, so it inherits the rest from dark.
const light = { ...dark, ...parseTheme(lightBlock) };

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r = 0, g = 0, b = 0] = channels.map((c) =>
    c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

describe.each([
  ["Saffron Night", dark],
  ["Fresh Market", light],
])("%s", (_name, theme) => {
  const token = (name: string): string => {
    const value = theme[name];
    if (!value) throw new Error(`missing ${name}`);
    // Surfaces are translucent and sit on the page background.
    return value.startsWith("rgba") ? over(value, token("--bg")) : value;
  };

  // ADR-0006 rule 6: save, skip and missing/call to action never share a colour.
  test("the meaning colours are distinct", () => {
    const meanings = ["--go", "--stop", "--accent"].map(token);
    expect(new Set(meanings).size).toBe(meanings.length);
  });

  // ADR-0006 rule 6: text meets WCAG AA (4.5:1) in both themes.
  test.each([
    ["--text", "--bg"],
    ["--text-muted", "--bg"],
    ["--accent", "--bg"],
    ["--stop", "--bg"],
    ["--go", "--bg"],
    ["--text", "--card"],
    ["--text-muted", "--card"],
    ["--accent", "--card"],
    ["--go", "--card"],
    ["--text", "--surface-strong"],
    ["--text-muted", "--surface-strong"],
    ["--accent", "--surface"],
    ["--accent", "--surface-strong"],
    ["--on-accent", "--accent"],
    ["--on-go", "--go"],
  ])("%s on %s meets AA", (fg, bg) => {
    expect(contrast(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5);
  });
});
