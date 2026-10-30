import type { RecipeCard } from "../api/client";
import { DishArt, IngredientArt } from "../art/IngredientArt";
import { DIETS } from "./diets";
import { listNames } from "./names";
import styles from "./RecipeFace.module.css";

/** The match ring: how much of the recipe's core the pantry covers. */
function MatchRing({ percentage }: { percentage: number }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const rounded = Math.round(percentage);
  return (
    <div className={styles.ring} aria-label={`${String(rounded)}% match`} role="img">
      <svg viewBox="0 0 64 64" width="72" height="72" aria-hidden="true">
        <circle cx="32" cy="32" r={radius} className={styles.ringTrack} />
        <circle
          cx="32"
          cy="32"
          r={radius}
          className={styles.ringFill}
          strokeDasharray={`${String((circumference * rounded) / 100)} ${String(circumference)}`}
        />
      </svg>
      <span className={styles.ringText} aria-hidden="true">
        {rounded}
        <small>%</small>
      </span>
    </div>
  );
}

/** What a recipe card shows: the dish, the match, and what you'd still need. */
export function RecipeFace({
  card,
  categories,
}: {
  card: RecipeCard;
  /** Each ingredient's category id, so its drawing can fall back to the category's. */
  categories: ReadonlyMap<string, string>;
}) {
  // A few of the matched ingredients float over the dish, as garnish.
  const garnish = card.matched_ingredients.slice(0, 3);
  const onlyMissing =
    card.missing_ingredients.length === 1 ? card.missing_ingredients[0] : null;

  return (
    <>
      <div className={styles.art}>
        <span className={styles.garnish}>
          {garnish.map((item) => (
            <IngredientArt
              key={item.id}
              ingredientId={item.id}
              categoryId={categories.get(item.id) ?? ""}
              size={46}
            />
          ))}
        </span>
        <DishArt recipeId={card.id} size={230} />
        {card.match_percentage === null ? (
          <span className={styles.basics}>Pantry basics</span>
        ) : (
          <MatchRing percentage={card.match_percentage} />
        )}
      </div>

      <div className={styles.body}>
        <h2 className={styles.name}>{card.name}</h2>
        <div className={styles.chips}>
          <span className={styles.chip}>
            <span aria-hidden="true">⏱</span> {card.total_minutes} min
          </span>
          <span className={styles.chip} data-diet={card.diet}>
            <span className={styles.dot} aria-hidden="true" />
            {DIETS[card.diet]}
          </span>
          {card.plan_ahead && (
            <span className={styles.chip} data-plan-ahead>
              <span aria-hidden="true">⏳</span> Plan ahead: {card.plan_ahead.note}
            </span>
          )}
        </div>

        {card.matched_ingredients.length > 0 ? (
          <p className={styles.have}>
            You have <strong>{listNames(card.matched_ingredients)}</strong>
            {card.assumed_staples.length > 0 && " + staples"}
          </p>
        ) : (
          <p className={styles.have}>Made from staples you already have</p>
        )}

        {onlyMissing ? (
          <p className={styles.nudge}>
            Add <strong>{onlyMissing.name.toLowerCase()}</strong>{" "}
            <span aria-hidden="true">→</span> 100% match
          </p>
        ) : (
          card.missing_ingredients.length > 0 && (
            <p className={styles.missing}>
              Missing <strong>{listNames(card.missing_ingredients)}</strong>
            </p>
          )
        )}
      </div>
    </>
  );
}
