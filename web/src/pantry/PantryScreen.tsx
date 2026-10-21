import { useMemo, useState } from "react";

import type { CatalogIngredient } from "../api/client";
import { useCatalog, useStaples } from "../api/queries";
import { useFlight } from "../motion/flightContext";
import { haptic } from "../motion/haptics";
import { useDevice } from "../store/device";
import { greetingFor } from "./greeting";
import { IngredientTile } from "./IngredientTile";
import { PantryDock } from "./PantryDock";
import styles from "./PantryScreen.module.css";
import { PantrySheet } from "./PantrySheet";
import { POPULAR, QUICK_STARTS } from "./presets";
import { QuickStarts } from "./QuickStarts";
import { searchIngredients } from "./search";
import { StaplesStrip } from "./StaplesStrip";

const POPULAR_TAB = "popular";

/** The first screen: tell the app what's in your kitchen. */
export function PantryScreen() {
  const catalog = useCatalog();
  const staples = useStaples();
  const {
    pantry,
    outOfStaples,
    addToPantry,
    removeFromPantry,
    clearPantry,
    toggleStaple,
  } = useDevice();
  const { launch } = useFlight();
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState(POPULAR_TAB);
  const [pantryOpen, setPantryOpen] = useState(false);
  const greeting = useMemo(() => greetingFor(new Date()), []);

  const ingredients = useMemo(() => catalog.data ?? [], [catalog.data]);
  const byId = useMemo(
    () => new Map(ingredients.map((item) => [item.id, item])),
    [ingredients],
  );
  // Ids this catalog doesn't list stay saved but aren't shown (ADR-0006 rule 5).
  const pantryItems = pantry.flatMap((id) => byId.get(id) ?? []);
  const inPantry = new Set(pantry);

  const categories = useMemo(() => {
    const seen = new Map<string, string>();
    for (const item of ingredients) seen.set(item.category.id, item.category.name);
    return [...seen].map(([id, name]) => ({ id, name }));
  }, [ingredients]);

  const presets = useMemo(
    () =>
      QUICK_STARTS.map((preset) => ({
        preset,
        items: preset.ingredientIds.flatMap((id) => byId.get(id) ?? []),
      })).filter(({ items }) => items.length > 0),
    [byId],
  );

  const shown: CatalogIngredient[] = query.trim()
    ? searchIngredients(ingredients, query)
    : tab === POPULAR_TAB
      ? POPULAR.flatMap((id) => byId.get(id) ?? [])
      : ingredients.filter((item) => item.category.id === tab);

  const stapleCount =
    (staples.data ?? []).reduce(
      (total, group) =>
        total +
        group.categories.reduce((sum, category) => sum + category.staples.length, 0),
      0,
    ) - outOfStaples.length;

  function toggle(ingredient: CatalogIngredient, art: Element | null) {
    haptic.tap();
    if (inPantry.has(ingredient.id)) {
      removeFromPantry(ingredient.id);
      return;
    }
    addToPantry([ingredient.id]);
    if (art) launch(art, ingredient.id, ingredient.category.id);
  }

  function pickPreset(items: readonly CatalogIngredient[], origin: Element) {
    haptic.tap();
    const added = items.filter((item) => !inPantry.has(item.id));
    addToPantry(added.map((item) => item.id));
    added.forEach((item, index) => {
      // A short stagger, so the ingredients fly as a stream, not a clump.
      window.setTimeout(() => {
        launch(origin, item.id, item.category.id);
      }, index * 70);
    });
  }

  return (
    <main className={styles.screen}>
      <header>
        <p className={styles.hello}>{greeting.hello}</p>
        <h1 className={styles.title}>
          What's for <span className={styles.meal}>{greeting.meal}</span>?
        </h1>
      </header>

      {presets.length > 0 && <QuickStarts presets={presets} onPick={pickPreset} />}

      <div className={styles.search}>
        <input
          type="search"
          className={styles.searchInput}
          placeholder="Search ingredients"
          aria-label="Search ingredients"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
      </div>

      {!query.trim() && categories.length > 0 && (
        <nav className={styles.tabs} aria-label="Browse by category">
          {[{ id: POPULAR_TAB, name: "Popular" }, ...categories].map((category) => (
            <button
              key={category.id}
              type="button"
              className={styles.tab}
              aria-pressed={tab === category.id}
              onClick={() => {
                setTab(category.id);
              }}
            >
              {category.name}
            </button>
          ))}
        </nav>
      )}

      {catalog.isPending && <p className={styles.status}>Loading ingredients…</p>}
      {catalog.isError && (
        <p className={styles.status} role="alert">
          We couldn't load the ingredients.{" "}
          <button
            type="button"
            className={styles.retry}
            onClick={() => {
              void catalog.refetch();
            }}
          >
            Try again
          </button>
        </p>
      )}
      {catalog.isSuccess && query.trim() !== "" && shown.length === 0 && (
        <p className={styles.status}>No ingredient matches “{query.trim()}”.</p>
      )}

      <div className={styles.grid}>
        {shown.map((ingredient) => (
          <IngredientTile
            key={ingredient.id}
            ingredient={ingredient}
            inPantry={inPantry.has(ingredient.id)}
            onToggle={toggle}
          />
        ))}
      </div>

      {staples.data && (
        <StaplesStrip
          groups={staples.data}
          outOf={outOfStaples}
          onToggle={toggleStaple}
        />
      )}

      <PantryDock
        items={pantryItems}
        stapleCount={Math.max(stapleCount, 0)}
        onOpenPantry={() => {
          setPantryOpen(true);
        }}
      />
      <PantrySheet
        open={pantryOpen}
        items={pantryItems}
        onClose={() => {
          setPantryOpen(false);
        }}
        onRemove={removeFromPantry}
        onClear={clearPantry}
      />
    </main>
  );
}
