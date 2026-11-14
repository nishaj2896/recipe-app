import { type ReactNode, useState } from "react";
import { Link } from "react-router";

import type { PairCard, RecipeIngredient } from "../api/client";
import { useCatalog, useRecipe, useStaples } from "../api/queries";
import { DishPhoto } from "../art/DishPhoto";
import { DishArt, IngredientArt } from "../art/IngredientArt";
import { DIETS } from "../deck/diets";
import { type Breaks, breaks, type FoodRules, keepsRules } from "../rules/check";
import { ALLERGENS, COURSES, DIET_CHOICES, dietChoice } from "../rules/labels";
import { type Allergen, useDevice } from "../store/device";
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
  const diet = useDevice((state) => state.diet);
  const jain = useDevice((state) => state.jain);
  const avoidAllergens = useDevice((state) => state.avoidAllergens);
  const avoidIngredients = useDevice((state) => state.avoidIngredients);
  const rules: FoodRules = { diet, jain, avoidAllergens, avoidIngredients };
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
  const broken = breaks(
    {
      diet: detail.diet,
      jain: detail.jain,
      allergens: detail.allergens.map((source) => source.allergen),
      ingredient_ids: detail.ingredients.map((item) => item.id),
    },
    rules,
  );
  // Each ingredient's tags: the avoided allergens it brings, or "Avoided".
  const tagsOf = (item: RecipeIngredient): string[] => [
    ...detail.allergens
      .filter(
        (source) =>
          broken.allergens.includes(source.allergen) &&
          source.ingredients.some((ref) => ref.id === item.id),
      )
      .map((source) => ALLERGENS[source.allergen]),
    ...(broken.ingredientIds.includes(item.id) ? ["Avoided"] : []),
  ];
  const pairs = detail.pairs_with.filter((pair) => keepsRules(pair, rules));
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
      <RulesNote
        broken={broken}
        rules={rules}
        sources={detail.allergens}
        ingredientName={(id) =>
          detail.ingredients.find((item) => item.id === id)?.name ?? id
        }
      />
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
                      <span className={styles.itemName}>
                        {item.name}
                        {tagsOf(item).map((tag) => (
                          <span key={tag} className={styles.warnTag}>
                            {tag}
                          </span>
                        ))}
                      </span>
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

      {pairs.length > 0 && (
        <section className={styles.group} aria-labelledby="pairs-title">
          <GroupTitle id="pairs-title" className={styles.groupTitle}>
            Pairs well with
          </GroupTitle>
          <ul className={styles.pairs}>
            {pairs.map((pair) => (
              <li key={pair.id}>
                <PairLink pair={pair} />
              </li>
            ))}
          </ul>
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

const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

function namesList(names: readonly string[]): string {
  return names.length < 2
    ? names.join("")
    : `${names.slice(0, -1).join(", ")} and ${names.at(-1) ?? ""}`;
}

/**
 * What in this recipe breaks the food rules, at the top of the recipe
 * (ADR-0012 rule 4). Search and saved recipes show every recipe, so this is
 * where the rules are said out loud.
 */
function RulesNote({
  broken,
  rules,
  sources,
  ingredientName,
}: {
  broken: Breaks;
  rules: FoodRules;
  sources: readonly { allergen: Allergen; ingredients: readonly { name: string }[] }[];
  ingredientName: (id: string) => string;
}) {
  const choice = DIET_CHOICES.find(
    (item) => item.id === dietChoice(rules.diet, rules.jain),
  );
  const notes: { title: string; text: string }[] = [
    ...broken.allergens.map((allergen) => {
      const label = lower(ALLERGENS[allergen]);
      const from = sources
        .find((source) => source.allergen === allergen)
        ?.ingredients.map((item) => lower(item.name));
      return {
        title: `Contains ${label}`,
        text: `This recipe uses ${namesList(from ?? [])}, and your food rules say you're allergic to ${label}.`,
      };
    }),
    ...broken.ingredientIds.map((id) => ({
      title: `Uses ${lower(ingredientName(id))}`,
      text: "Your food rules say you avoid it.",
    })),
    ...(broken.diet || broken.jain
      ? [
          {
            title: "Not for your diet",
            text: `Your food rules say ${choice?.label ?? "a diet"}: ${lower(choice?.hint ?? "")}.`,
          },
        ]
      : []),
  ];
  if (notes.length === 0) return null;
  return (
    <div className={styles.rulesNote} role="note">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 3L2 20h20z" />
        <path d="M12 10v4M12 17h.01" />
      </svg>
      <div className={styles.rulesText}>
        {notes.map((note) => (
          <p key={note.title}>
            <strong>{note.title}</strong> {note.text}
          </p>
        ))}
        <p>
          It won't appear in your deck.
          {broken.allergens.length > 0 &&
            " Ready-made items can hide allergens too, so check their labels."}
        </p>
      </div>
    </div>
  );
}

/** One "pairs well with" pick: its photo, name, course and time. */
function PairLink({ pair }: { pair: PairCard }) {
  const course = pair.courses[0];
  return (
    <Link to={`/recipe/${pair.id}`} className={styles.pair}>
      {pair.image ? (
        <DishPhoto
          {...pair.image}
          alt=""
          recipeId={pair.id}
          className={styles.pairPhoto}
          artSize={96}
        />
      ) : (
        <DishArt recipeId={pair.id} size={96} />
      )}
      <span className={styles.pairName}>{pair.name}</span>
      <span className={styles.pairMeta}>
        {course ? `${COURSES[course]} · ` : ""}
        {pair.total_minutes} min
      </span>
    </Link>
  );
}
