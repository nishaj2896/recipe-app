import { type ReactNode, useState } from "react";

import type { RecipeIngredient } from "../api/client";
import { useCatalog, useRecipe, useStaples } from "../api/queries";
import { DishPhoto } from "../art/DishPhoto";
import { DishArt, IngredientArt } from "../art/IngredientArt";
import { DIETS } from "../deck/diets";
import { useDevice } from "../store/device";
import styles from "./RecipeDetail.module.css";
import { MAX_SERVINGS, MIN_SERVINGS, scaledAmount } from "./scale";
import { formatWait } from "./wait";

interface Props {
  recipeId: string;
  /** Replaces the save button, as the deck does with its own Skip and Save. */
  actions?: ReactNode;
  /** Inside a sheet, which has its own h2 title, the headings start one level down. */
  nested?: boolean;
}

/**
 * A recipe's photo, ingredients sorted into what you have and what you'd
 * need, with amounts for the servings chosen, and its method (ADR-0008 rule 8).
 */
export function RecipeDetail({ recipeId, actions, nested = false }: Props) {
  const Name = nested ? "h3" : "h1";
  const GroupTitle = nested ? "h4" : "h2";
  const recipe = useRecipe(recipeId);
  const catalog = useCatalog();
  const staples = useStaples();
  const pantry = useDevice((state) => state.pantry);
  const outOfStaples = useDevice((state) => state.outOfStaples);
  const saved = useDevice((state) => state.saved);
  // Not saved: each recipe opens at its written size (ADR-0008 rule 8). The
  // id keeps a choice from carrying over when the deck shows the next recipe.
  const [chosen, setChosen] = useState<{ recipeId: string; servings: number } | null>(
    null,
  );
  const { saveRecipe, unsaveRecipe } = useDevice.getState();

  // Without the staples, every staple would flash under "You'll need".
  if (recipe.isPending || staples.isPending) {
    return <p className={styles.status}>Loading the recipe…</p>;
  }
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

  const groups: [string, RecipeIngredient[]][] = [
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
  const serves = detail.serves;
  const shownServings = chosen?.recipeId === detail.id ? chosen.servings : serves;
  const setServings = (servings: number) => {
    setChosen({ recipeId: detail.id, servings });
  };
  const amountOf = (item: RecipeIngredient) => {
    if (serves === null || shownServings === null) return null;
    if (item.amount === null || item.unit === null) return "to taste";
    return scaledAmount(item.amount, item.unit, serves, shownServings);
  };

  return (
    <article className={styles.detail} aria-labelledby="recipe-name">
      <div className={styles.art}>
        {detail.image ? (
          <DishPhoto
            key={detail.image.url}
            {...detail.image}
            recipeId={detail.id}
            className={styles.photo}
            artSize={220}
          />
        ) : (
          <DishArt recipeId={detail.id} size={220} />
        )}
      </div>
      <Name id="recipe-name" className={styles.name}>
        {detail.name}
      </Name>
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
      {detail.plan_ahead && (
        <p className={styles.planAhead}>
          <strong>Plan ahead: {detail.plan_ahead.note}.</strong> About{" "}
          {formatWait(detail.plan_ahead.wait_minutes)} hands-off, not counted in the times
          above.
        </p>
      )}

      {serves !== null && shownServings !== null && (
        <div className={styles.servings} role="group" aria-label="Servings">
          <span className={styles.servingsLabel}>Serves</span>
          <button
            type="button"
            className={styles.stepper}
            aria-label="Fewer servings"
            disabled={shownServings <= MIN_SERVINGS}
            onClick={() => {
              setServings(Math.max(MIN_SERVINGS, shownServings - 1));
            }}
          >
            −
          </button>
          <output className={styles.servingsCount} aria-live="polite">
            {shownServings}
          </output>
          <button
            type="button"
            className={styles.stepper}
            aria-label="More servings"
            disabled={shownServings >= MAX_SERVINGS}
            onClick={() => {
              setServings(Math.min(MAX_SERVINGS, shownServings + 1));
            }}
          >
            +
          </button>
        </div>
      )}

      {groups.map(
        ([title, items]) =>
          items.length > 0 && (
            <section key={title} className={styles.group} aria-label={title}>
              <GroupTitle className={styles.groupTitle}>{title}</GroupTitle>
              <ul className={styles.list}>
                {items.map((item) => {
                  const amount = amountOf(item);
                  return (
                    <li key={item.id} className={styles.item}>
                      <IngredientArt
                        ingredientId={item.id}
                        categoryId={categoryOf.get(item.id) ?? ""}
                        size={32}
                      />
                      <span className={styles.itemName}>{item.name}</span>
                      {amount !== null && <span className={styles.amount}>{amount}</span>}
                    </li>
                  );
                })}
              </ul>
            </section>
          ),
      )}

      {detail.steps.length > 0 && (
        <section className={styles.group} aria-label="Method">
          <GroupTitle className={styles.groupTitle}>Method</GroupTitle>
          <ol className={styles.method}>
            {detail.steps.map((step, index) => (
              <li key={index} className={styles.step}>
                {step}
              </li>
            ))}
          </ol>
        </section>
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
