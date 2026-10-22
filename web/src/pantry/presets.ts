import presets from "./presets.json";

/**
 * The ingredient list the pantry offers before the user types anything. It
 * lives in JSON so the Python tests can check every id against the catalog
 * (tests/test_web_presets.py).
 */

/** What the pantry grid shows before the user types or picks a category. */
export const POPULAR: readonly string[] = presets.popular;
