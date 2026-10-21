import { AnimatePresence, m } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";

import type { RecipeCard } from "../api/client";
import { useCatalog } from "../api/queries";
import { greetingFor } from "../pantry/greeting";
import { useDevice } from "../store/device";
import { CookingScene } from "./CookingScene";
import styles from "./DeckScreen.module.css";
import { Recap } from "./Recap";
import { RecipeFace } from "./RecipeFace";
import { searchFor } from "./searchRequest";
import type { Direction } from "./swipe";
import { SwipeCard, type SwipeCardHandle } from "./SwipeCard";
import { SearchError, useDeck } from "./useDeck";

interface Swipe {
  id: string;
  direction: Direction;
}

/** Cards drawn under the top one, to show the deck's depth. */
const STACK = 3;

/** The swipe deck: right to save, left to skip, one deck of 20 at a time. */
export function DeckScreen() {
  const hydration = useDevice((state) => state.hydration);
  const saved = useDevice((state) => state.saved);
  const hidden = useDevice((state) => state.hidden);
  const pantry = useDevice((state) => state.pantry);
  const { saveRecipe, unsaveRecipe, hideRecipe, unhideRecipe, removeFromPantry } =
    useDevice.getState();
  const catalog = useCatalog();
  const loaded = hydration !== "pending";

  // The search and what was saved before are read once, when the deck opens:
  // swiping changes both, and the deck must not reshuffle under the finger.
  const search = useMemo(
    () => (loaded ? searchFor(useDevice.getState()) : undefined),
    [loaded],
  );
  const savedOnOpen = useMemo(
    () => (loaded ? new Set(useDevice.getState().saved) : new Set<string>()),
    [loaded],
  );
  // A fresh deck is read again: it can deal recipes saved earlier this visit.
  const [savedOnFreshDeck, setSavedOnFreshDeck] = useState<Set<string> | null>(null);
  const savedBefore = savedOnFreshDeck ?? savedOnOpen;

  const [round, setRound] = useState(0);
  const [deckIndex, setDeckIndex] = useState(0);
  const [history, setHistory] = useState<Swipe[]>([]);
  const [sceneDoneFor, setSceneDoneFor] = useState<string | null>(null);
  const top = useRef<SwipeCardHandle>(null);
  const meal = useMemo(() => greetingFor(new Date()).meal, []);

  const deck = useDeck(search ?? null, round);
  const pages = deck.data?.pages ?? [];
  const page = pages[deckIndex];
  const dealKey = `${String(round)}:${String(deckIndex)}`;

  const byId = useMemo(
    () => new Map((catalog.data ?? []).map((item) => [item.id, item])),
    [catalog.data],
  );
  const categories = useMemo(
    () => new Map([...byId].map(([id, item]) => [id, item.category.id])),
    [byId],
  );

  // Pantry ids the API now ignores (retired, or now a staple) leave the
  // pantry, and the user is told which (ADR-0006 rule 5). Only ids sent as
  // pantry count: a retired out-of-stock staple was never in the pantry.
  const firstPage = pages[0];
  const ignored = useMemo(
    () =>
      (firstPage?.ignored_ingredients ?? []).filter(
        (item) =>
          item.reason !== "not_staple" && search?.ingredient_ids.includes(item.id),
      ),
    [firstPage, search],
  );
  useEffect(() => {
    for (const item of ignored) {
      if (useDevice.getState().pantry.includes(item.id)) removeFromPantry(item.id);
    }
  }, [ignored, removeFromPantry]);

  const finishScene = useCallback(() => {
    setSceneDoneFor(dealKey);
  }, [dealKey]);

  const savedNow = new Set(saved);
  const hiddenNow = new Set(hidden);
  const dealt = (page?.results ?? []).filter((card) => !savedBefore.has(card.id));
  const remaining = dealt.filter(
    (card) => !savedNow.has(card.id) && !hiddenNow.has(card.id),
  );
  const current = remaining[0];
  const dealtIds = new Set(dealt.map((card) => card.id));
  const swipesHere = history.filter((swipe) => dealtIds.has(swipe.id));
  const savedHere = dealt.filter(
    (card) => savedNow.has(card.id) && swipesHere.some((swipe) => swipe.id === card.id),
  );

  const waiting = search !== null && search !== undefined && !page && !deck.isError;
  const showScene = waiting || (page !== undefined && sceneDoneFor !== dealKey);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      // Alt or Cmd with an arrow is the browser's back and forward, and a held
      // key repeats: neither should skip a card.
      if (
        event.repeat ||
        event.altKey ||
        event.metaKey ||
        event.ctrlKey ||
        event.defaultPrevented
      ) {
        return;
      }
      if (event.key === "ArrowRight") top.current?.fling("right");
      if (event.key === "ArrowLeft") top.current?.fling("left");
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  function swiped(card: RecipeCard, direction: Direction) {
    if (direction === "right") {
      // The first save asks the browser to keep this site's storage
      // (ADR-0006 rule 5); browsers that don't support it just carry on.
      if (useDevice.getState().saved.length === 0)
        void (navigator.storage as StorageManager | undefined)?.persist();
      saveRecipe(card.id);
    } else {
      hideRecipe(card.id);
    }
    setHistory((past) => [...past, { id: card.id, direction }]);
  }

  function undo() {
    const last = swipesHere.at(-1);
    if (!last) return;
    if (last.direction === "right") unsaveRecipe(last.id);
    else unhideRecipe(last.id);
    setHistory((past) => past.filter((swipe) => swipe !== last));
  }

  function dealMore() {
    setDeckIndex((index) => index + 1);
    if (pages.length <= deckIndex + 1) void deck.fetchNextPage();
  }

  function startOver() {
    setSavedOnFreshDeck(new Set(useDevice.getState().saved));
    setRound((value) => value + 1);
    setDeckIndex(0);
  }

  if (search === null) {
    return (
      <main className={styles.screen}>
        <div className={styles.empty}>
          <h1 className={styles.emptyTitle}>Your pantry is empty</h1>
          <p className={styles.muted}>
            Add a few ingredients and we'll find what you can cook.
          </p>
          <Link to="/" className={styles.primary}>
            Fill your pantry
          </Link>
        </div>
      </main>
    );
  }

  const position = Math.min(dealt.length - remaining.length + 1, dealt.length);

  return (
    <main className={styles.screen}>
      <header className={styles.header}>
        <Link to="/" className={styles.back} aria-label="Back to your pantry">
          <span aria-hidden="true">←</span>
        </Link>
        <div className={styles.heading}>
          <p className={styles.eyebrow}>
            {current
              ? `Your deck · ${String(position)} of ${String(dealt.length)}`
              : "Your deck"}
          </p>
          <h1 className={styles.title}>
            {meal.charAt(0).toUpperCase() + meal.slice(1)} picks
          </h1>
        </div>
        <m.span
          key={saved.length}
          className={styles.hearts}
          aria-label={`${String(saved.length)} saved`}
          role="img"
          initial={{ scale: saved.length > 0 ? 1.35 : 1 }}
          animate={{ scale: 1 }}
        >
          <span aria-hidden="true">♥</span> {saved.length}
        </m.span>
      </header>
      {dealt.length > 0 && current && (
        <div className={styles.progress} aria-hidden="true">
          <m.span
            className={styles.progressFill}
            animate={{ scaleX: (position - 1) / dealt.length }}
          />
        </div>
      )}

      {ignored.length > 0 && (
        <p className={styles.notice} role="status">
          We took {ignored.map((item) => item.name.toLowerCase()).join(", ")} out of your
          pantry: {ignored.length === 1 ? "it's" : "they're"} now assumed or no longer
          used.
        </p>
      )}

      {deck.isError && !page && (
        <div className={styles.empty} role="alert">
          {deck.error instanceof SearchError && deck.error.cursorRefused ? (
            <>
              <p>This deck has gone stale.</p>
              <button type="button" className={styles.primary} onClick={startOver}>
                Deal a fresh deck
              </button>
            </>
          ) : (
            <>
              <p>We couldn't find recipes just now.</p>
              <button
                type="button"
                className={styles.primary}
                onClick={() => {
                  void (pages.length > 0 ? deck.fetchNextPage() : deck.refetch());
                }}
              >
                Try again
              </button>
            </>
          )}
        </div>
      )}

      {page && !showScene && (
        <>
          {current ? (
            <>
              <div className={styles.stack}>
                {remaining
                  .slice(1, STACK)
                  .reverse()
                  .map((card) => {
                    const depth = remaining.indexOf(card);
                    return (
                      <m.div
                        key={card.id}
                        className={styles.under}
                        aria-hidden="true"
                        animate={{ scale: 1 - depth * 0.05, y: depth * 16 }}
                      >
                        <RecipeFace card={card} categories={categories} />
                      </m.div>
                    );
                  })}
                <SwipeCard
                  key={current.id}
                  ref={top}
                  label={current.name}
                  onSwipe={(direction) => {
                    swiped(current, direction);
                  }}
                >
                  <RecipeFace card={current} categories={categories} />
                </SwipeCard>
              </div>
              <p className={styles.hint}>Swipe right to save, left to skip</p>
              <div className={styles.controls}>
                <button
                  type="button"
                  className={styles.round}
                  data-kind="undo"
                  aria-label="Undo last swipe"
                  disabled={swipesHere.length === 0}
                  onClick={undo}
                >
                  ↺
                </button>
                <button
                  type="button"
                  className={styles.round}
                  data-kind="skip"
                  aria-label={`Skip ${current.name}`}
                  onClick={() => top.current?.fling("left")}
                >
                  ✕
                </button>
                <button
                  type="button"
                  className={styles.round}
                  data-kind="save"
                  aria-label={`Save ${current.name}`}
                  onClick={() => top.current?.fling("right")}
                >
                  ♥
                </button>
              </div>
            </>
          ) : dealt.length === 0 && deckIndex === 0 ? (
            <div className={styles.empty}>
              <h2 className={styles.emptyTitle}>Nothing to cook yet</h2>
              <p className={styles.muted}>
                No recipe matches this pantry. Add a few more ingredients and try again.
              </p>
              <Link to="/" className={styles.primary}>
                Add ingredients
              </Link>
            </div>
          ) : (
            <Recap
              dealt={dealt.length}
              saved={savedHere}
              hasMore={page.next_cursor !== null}
              onDealMore={dealMore}
              byId={byId}
            />
          )}
        </>
      )}

      <AnimatePresence>
        {showScene && !deck.isError && (
          <CookingScene
            key={dealKey}
            ingredients={pantry.flatMap((id) => byId.get(id) ?? [])}
            waiting={waiting}
            onDone={finishScene}
          />
        )}
      </AnimatePresence>
    </main>
  );
}
