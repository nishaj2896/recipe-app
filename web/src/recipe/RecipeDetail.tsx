import type { ReactNode } from "react";

import type { IngredientRef } from "../api/client";
import { useCatalog, useRecipe, useStaples } from "../api/queries";
import { DishArt, IngredientArt } from "../art/IngredientArt";
import { DIETS } from "../deck/diets";
import { useDevice } from "../store/device";
import styles from "./RecipeDetail.module.css";

interface Props {
  recipeId: string;
  /** Replaces the save button, as the deck does with its own Skip and Save. */
  actions?: ReactNode;
}

/** A recipe's full ingredient list, sorted into what you have and what you'd need. */
export function RecipeDetail({ recipeId, actions }: Props) {
  const recipe = useRecipe(recipeId);
  const catalog = useCatalog();
  const staples = useStaples();
  const pantry = useDevice((state) => state.pantry);
  const outOfStaples = useDevice((state) => state.outOfStaples);
  const saved = useDevice((state) => state.saved);
  const { saveRecipe, unsaveRecipe } = useDevice.getState();

  if (recipe.isPending) return <p className={styles.status}>Loading the recipe…</p>;
  if (recipe.isError) {
    return (
      <p className={styles.status} role="alert">
        We couldn't load this recipe.{" "}
        <button
          type="button"
          className={styles.retry}
          onClick={() => {
            void recipe.refetch();
          }}
        >
          Try again
        </button>
      </p>
    );
  }
  if (recipe.data === null) {
    return (
      <p className={styles.status}>
        This recipe isn't available right now. It stays in your saved recipes, and we'll
        try again next time.
      </p>
    );
  }

  const detail = recipe.data;
  const have = new Set(pantry);
  const out = new Set(outOfStaples);
  const stapleIds = new Set(
    (staples.data ?? []).flatMap((group) =>
      group.categories.flatMap((category) => category.staples.map((staple) => staple.id)),
    ),
  );
  const categoryOf = new Map(
    (catalog.data ?? []).map((item) => [item.id, item.category.id]),
  );

  const groups: [string, IngredientRef[]][] = [
    ["You have", detail.ingredients.filter((item) => have.has(item.id))],
    [
      "You'll need",
      detail.ingredients.filter(
        (item) => !have.has(item.id) && (!stapleIds.has(item.id) || out.has(item.id)),
      ),
    ],
    [
      "Staples we assume you have",
      detail.ingredients.filter(
        (item) => !have.has(item.id) && stapleIds.has(item.id) && !out.has(item.id),
      ),
    ],
  ];
  const isSaved = saved.includes(detail.id);

  return (
    <article className={styles.detail} aria-labelledby="recipe-name">
      <div className={styles.art}>
        <DishArt recipeId={detail.id} size={220} />
      </div>
      <h1 id="recipe-name" className={styles.name}>
        {detail.name}
      </h1>
      <dl className={styles.times}>
        <div>
          <dt>Prep</dt>
          <dd>{detail.prep_minutes} min</dd>
        </div>
        <div>
          <dt>Cook</dt>
          <dd>{detail.cook_minutes} min</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>{detail.total_minutes} min</dd>
        </div>
        <div>
          <dt>Diet</dt>
          <dd>{DIETS[detail.diet]}</dd>
        </div>
      </dl>

      {groups.map(
        ([title, items]) =>
          items.length > 0 && (
            <section key={title} className={styles.group} aria-label={title}>
              <h2 className={styles.groupTitle}>{title}</h2>
              <ul className={styles.list}>
                {items.map((item) => (
                  <li key={item.id} className={styles.item}>
                    <IngredientArt
                      ingredientId={item.id}
                      categoryId={categoryOf.get(item.id) ?? ""}
                      size={32}
                    />
                    {item.name}
                  </li>
                ))}
              </ul>
            </section>
          ),
      )}

      <div className={styles.actions}>
        {actions ?? (
          <button
            type="button"
            className={styles.save}
            aria-pressed={isSaved}
            onClick={() => {
              if (isSaved) unsaveRecipe(detail.id);
              else saveRecipe(detail.id);
            }}
          >
            {isSaved ? "♥ Saved" : "♡ Save"}
          </button>
        )}
      </div>
    </article>
  );
}
