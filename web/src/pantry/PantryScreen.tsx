import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";

import type { CatalogIngredient } from "../api/client";
import { useCatalog, useStaples } from "../api/queries";
import { useFlight } from "../motion/flightContext";
import { haptic } from "../motion/haptics";
import { useDevice } from "../store/device";
import { greetingFor } from "./greeting";
import { IngredientTile } from "./IngredientTile";
import { PantryDock } from "./PantryDock";
import styles from "./PantryScreen.module.css";
import { Sheet } from "../app/Sheet";
import { PantrySheet } from "./PantrySheet";
import { POPULAR, QUICK_STARTS } from "./presets";
import { QuickStarts } from "./QuickStarts";
import { searchIngredients } from "./search";
import { type Listening, useSpeech } from "./speech";
import { findSpoken } from "./spoken";
import { StaplesStrip } from "./StaplesStrip";
import { VoiceAdd } from "./VoiceAdd";

const POPULAR_TAB = "popular";

/** Something a spoken sentence can name: an ingredient, or a staple. */
interface Nameable {
  name: string;
  otherNames: readonly string[];
  ingredient: CatalogIngredient | null;
}

/** What the last spoken sentence added, for the status line. */
interface VoiceResult {
  sentence: string;
  added: string[];
  already: string[];
  staples: string[];
}

const list = (names: readonly string[]) =>
  names.length < 2
    ? names.join("")
    : `${names.slice(0, -1).join(", ")} and ${names.at(-1) ?? ""}`;

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
    hydration,
    saved,
    voiceNoticeSeen,
    markVoiceNoticeSeen,
  } = useDevice();
  const { launch } = useFlight();
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState(POPULAR_TAB);
  const [pantryOpen, setPantryOpen] = useState(false);
  const greeting = useMemo(() => greetingFor(new Date()), []);
  const staggered = useRef<number[]>([]);
  const mic = useRef<HTMLButtonElement>(null);
  const [voiceResult, setVoiceResult] = useState<VoiceResult | null>(null);
  const speech = useSpeech(heard);
  const [voiceNoticeOpen, setVoiceNoticeOpen] = useState(false);

  function listen() {
    setVoiceResult(null);
    speech.start();
  }

  useEffect(
    () => () => {
      staggered.current.forEach((id) => {
        window.clearTimeout(id);
      });
    },
    [],
  );

  // Taps wait until the saved pantry has been read, so a tap can't race it
  // (the store refuses writes before then anyway).
  const loaded = hydration !== "pending";

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

  // Out-of-stock ids are kept even when a staple leaves the list (ADR-0006
  // rule 5), so count the listed staples rather than subtract.
  const stapleCount = (staples.data ?? [])
    .flatMap((group) => group.categories.flatMap((category) => category.staples))
    .filter((staple) => !outOfStaples.includes(staple.id)).length;

  function toggle(ingredient: CatalogIngredient, art: Element | null) {
    haptic.tap();
    if (inPantry.has(ingredient.id)) {
      removeFromPantry(ingredient.id);
      return;
    }
    if (!art) {
      addToPantry([ingredient.id]);
      return;
    }
    launch(art, ingredient.id, ingredient.category.id);
    // The flight starts this frame; the pantry re-renders in the next task,
    // so the two never block one frame together (ADR-0006 rule 10).
    window.setTimeout(() => {
      addToPantry([ingredient.id]);
    });
  }

  // Staples are named too, so "onions" is answered rather than ignored.
  const nameables = useMemo<Nameable[]>(
    () => [
      ...ingredients.map((item) => ({
        name: item.name,
        otherNames: item.search_terms,
        ingredient: item,
      })),
      ...(staples.data ?? []).flatMap((group) =>
        group.categories.flatMap((category) =>
          category.staples.map((staple) => ({
            name: staple.name,
            otherNames: [],
            ingredient: null,
          })),
        ),
      ),
    ],
    [ingredients, staples.data],
  );

  function heard(sentence: string) {
    const found = findSpoken(nameables, sentence, (item) => item.otherNames);
    const items = found.flatMap((item) => item.ingredient ?? []);
    const current = new Set(useDevice.getState().pantry);
    setVoiceResult({
      sentence,
      added: items.filter((item) => !current.has(item.id)).map((item) => item.name),
      already: items.filter((item) => current.has(item.id)).map((item) => item.name),
      staples: found.filter((item) => !item.ingredient).map((item) => item.name),
    });
    if (mic.current) pickPreset(items, mic.current);
  }

  function pickPreset(items: readonly CatalogIngredient[], origin: Element) {
    haptic.tap();
    const added = items.filter((item) => !inPantry.has(item.id));
    addToPantry(added.map((item) => item.id));
    added.forEach((item, index) => {
      // A short stagger, so the ingredients fly as a stream, not a clump.
      const id = window.setTimeout(() => {
        if (origin.isConnected) launch(origin, item.id, item.category.id);
      }, index * 70);
      staggered.current.push(id);
    });
  }

  return (
    <main className={styles.screen}>
      <header className={styles.header}>
        {saved.length > 0 && (
          <Link
            to="/saved"
            className={styles.cookbook}
            aria-label={`Your cookbook: ${String(saved.length)} saved`}
          >
            <span aria-hidden="true">♥</span> {saved.length}
          </Link>
        )}
        <p className={styles.hello}>{greeting.hello}</p>
        <h1 className={styles.title}>
          What's for <span className={styles.meal}>{greeting.meal}</span>?
        </h1>
      </header>

      {hydration === "failed" && (
        <p className={styles.warning} role="alert">
          We couldn't read the pantry saved on this phone. You can still pick ingredients,
          but they won't be saved this visit.
        </p>
      )}

      {loaded && presets.length > 0 && (
        <QuickStarts presets={presets} onPick={pickPreset} />
      )}

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
        {/* Only once everything a sentence can name has loaded. */}
        {speech.supported && loaded && catalog.isSuccess && staples.isSuccess && (
          <VoiceAdd
            ref={mic}
            listening={speech.listening.state === "listening"}
            onStart={() => {
              // Before the first use, say where the voice goes.
              if (voiceNoticeSeen) listen();
              else setVoiceNoticeOpen(true);
            }}
            onStop={speech.stop}
          />
        )}
      </div>
      <VoiceStatus listening={speech.listening} result={voiceResult} />
      <Sheet
        open={voiceNoticeOpen}
        onClose={() => {
          setVoiceNoticeOpen(false);
        }}
        title="Before you speak"
      >
        <p className={styles.noticeText}>
          Your browser sends what you say to its speech service (for example Google or
          Apple) to turn it into text. This app only gets the text.
        </p>
        <button
          type="button"
          className={styles.noticeOk}
          onClick={() => {
            markVoiceNoticeSeen();
            setVoiceNoticeOpen(false);
            listen();
          }}
        >
          OK, start listening
        </button>
      </Sheet>

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

      {(catalog.isPending || !loaded) && !catalog.isError && (
        <p className={styles.status}>Loading ingredients…</p>
      )}
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
        {loaded &&
          shown.map((ingredient) => (
            <IngredientTile
              key={ingredient.id}
              ingredient={ingredient}
              inPantry={inPantry.has(ingredient.id)}
              onToggle={toggle}
            />
          ))}
      </div>

      {loaded && staples.data && (
        <StaplesStrip
          groups={staples.data}
          outOf={outOfStaples}
          onToggle={toggleStaple}
        />
      )}

      <PantryDock
        items={pantryItems}
        stapleCount={stapleCount}
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

function VoiceStatus({
  listening,
  result,
}: {
  listening: Listening;
  result: VoiceResult | null;
}) {
  let text: string | null = null;
  if (listening.state === "listening") {
    text = listening.heard ? `“${listening.heard}”` : "Listening… say what you have";
  } else if (listening.state === "blocked") {
    text = "The microphone is off for this site. You can type instead.";
  } else if (listening.state === "failed") {
    text = "We couldn't hear that. Try again, or type instead.";
  } else if (result) {
    const parts = [
      result.added.length > 0 && `Added ${list(result.added).toLowerCase()}.`,
      result.already.length > 0 &&
        `${list(result.already)} ${result.already.length === 1 ? "was" : "were"} already in.`,
      result.staples.length > 0 &&
        `${list(result.staples)} ${result.staples.length === 1 ? "is a staple" : "are staples"}: we assume you have ${result.staples.length === 1 ? "it" : "them"}.`,
    ].filter(Boolean);
    text =
      parts.length > 0
        ? parts.join(" ")
        : `We didn't find an ingredient in “${result.sentence}”. Try saying just the names.`;
  }
  return (
    <p className={styles.voice} role="status">
      {text}
    </p>
  );
}
