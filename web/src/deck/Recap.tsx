import { useState } from "react";
import { Link } from "react-router";

import type { CatalogIngredient, RecipeCard } from "../api/client";
import { DishArt, IngredientArt } from "../art/IngredientArt";
import { InstallNudge } from "../install/InstallNudge";
import styles from "./Recap.module.css";
import { shoppingList, shoppingText } from "./shopping";

interface Props {
  dealt: number;
  saved: readonly RecipeCard[];
  /** Another deck is ready to deal: false once every recipe has been shown. */
  hasMore: boolean;
  onDealMore: () => void;
  byId: ReadonlyMap<string, CatalogIngredient>;
}

/** The end of a deck: what you saved, and what to buy to cook it. */
export function Recap({ dealt, saved, hasMore, onDealMore, byId }: Props) {
  const items = shoppingList(saved);
  const [shared, setShared] = useState<"copied" | "failed" | null>(null);

  async function share() {
    const text = shoppingText(items);
    try {
      if (typeof navigator.share === "function") {
        await navigator.share({ title: "Shopping list", text });
        return;
      }
      await navigator.clipboard.writeText(text);
      setShared("copied");
    } catch (error) {
      // Closing the share sheet isn't a failure.
      if (error instanceof DOMException && error.name === "AbortError") return;
      setShared("failed");
    }
  }

  return (
    <section className={styles.recap} aria-labelledby="recap-title">
      <DishArt recipeId={saved[0]?.id ?? "recap"} size={200} />
      <h1 id="recap-title" className={styles.title}>
        {hasMore ? (
          <>
            That's your <span className={styles.count}>{dealt}</span>
          </>
        ) : (
          "That's every match"
        )}
      </h1>
      <p className={styles.subtitle}>
        {saved.length === 0
          ? hasMore
            ? "Nothing caught your eye this time."
            : "You've seen every recipe your pantry can make."
          : `You saved ${String(saved.length)} ${saved.length === 1 ? "recipe" : "recipes"}.`}
      </p>
      {saved.length > 0 && <InstallNudge />}

      {items.length > 0 && (
        <div className={styles.list}>
          <h2 className={styles.listTitle}>Shopping list from your saves</h2>
          <ul>
            {items.map((item) => (
              <li key={item.ingredient.id} className={styles.item}>
                <IngredientArt
                  ingredientId={item.ingredient.id}
                  categoryId={byId.get(item.ingredient.id)?.category.id ?? ""}
                  size={32}
                />
                <span className={styles.itemName}>{item.ingredient.name}</span>
                <span className={styles.itemCount}>
                  {item.recipes} {item.recipes === 1 ? "recipe" : "recipes"}
                </span>
              </li>
            ))}
          </ul>
          <button type="button" className={styles.share} onClick={() => void share()}>
            Share list
          </button>
          {shared && (
            <p className={styles.shared} role="status">
              {shared === "copied"
                ? "Copied to your clipboard."
                : "Couldn't share the list."}
            </p>
          )}
        </div>
      )}

      {hasMore ? (
        <button type="button" className={styles.more} onClick={onDealMore}>
          Deal more
        </button>
      ) : (
        <Link to="/" className={styles.more}>
          Add ingredients for more
        </Link>
      )}
      <Link to="/saved" className={styles.back}>
        Open your cookbook <span aria-hidden="true">→</span>
      </Link>
      <Link to="/" className={styles.back}>
        Back to your pantry
      </Link>
    </section>
  );
}
