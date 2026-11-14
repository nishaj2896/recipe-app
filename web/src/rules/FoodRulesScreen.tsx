import { useMemo, useState } from "react";

import { useIngredients } from "../api/queries";
import { BackArrow } from "../app/BackArrow";
import { useLeave } from "../app/leave";
import { MAX_AVOIDED_INGREDIENTS } from "../deck/searchRequest";
import { searchIngredients } from "../pantry/search";
import { type Allergen, useDevice } from "../store/device";
import styles from "./Choices.module.css";
import { ALLERGENS, DIET_CHOICES, dietChoice, fromDietChoice, keysOf } from "./labels";

/**
 * The food rules (ADR-0012 rules 4 and 12): a diet, allergies and any other
 * ingredient to avoid. The deck never deals a recipe that breaks them.
 * Nothing is stored until Save, so Back keeps the rules as they were.
 */
export function FoodRulesScreen() {
  const hydration = useDevice((state) => state.hydration);
  // The form starts from the stored rules once they've been read.
  return hydration === "pending" ? null : <FoodRulesForm />;
}

function FoodRulesForm() {
  const stored = useDevice.getState();
  const { setFoodRules, markFoodRulesSeen } = stored;
  const firstTime = !stored.foodRulesSeen;
  const leave = useLeave();
  const ingredients = useIngredients();
  const [diet, setDiet] = useState(dietChoice(stored.diet, stored.jain));
  const [allergens, setAllergens] = useState<readonly Allergen[]>(stored.avoidAllergens);
  const [avoided, setAvoided] = useState<readonly string[]>(stored.avoidIngredients);
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState("");

  const byId = useMemo(
    () => new Map((ingredients.data ?? []).map((item) => [item.id, item])),
    [ingredients.data],
  );
  const live = useMemo(
    () => (ingredients.data ?? []).filter((item) => !avoided.includes(item.id)),
    [ingredients.data, avoided],
  );
  const matches = searchIngredients(live, query, 8);
  const count = allergens.length + avoided.length;

  function toggleAllergen(allergen: Allergen) {
    setAllergens((list) =>
      list.includes(allergen)
        ? list.filter((item) => item !== allergen)
        : [...list, allergen],
    );
  }

  function save() {
    setFoodRules({
      ...fromDietChoice(diet),
      avoidAllergens: [...allergens],
      avoidIngredients: avoided.slice(-MAX_AVOIDED_INGREDIENTS),
    });
    leave();
  }

  return (
    <main className={styles.screen}>
      <div className={styles.body}>
        <header>
          <div className={styles.top}>
            {!firstTime && (
              <button
                type="button"
                className={styles.back}
                aria-label="Back without saving"
                onClick={leave}
              >
                <BackArrow />
              </button>
            )}
            <p className={styles.eyebrow}>{firstTime ? "Set up once" : "Your profile"}</p>
          </div>
          <h1 className={styles.title}>Your food rules</h1>
          <p className={styles.lead}>
            The deck never shows a recipe that breaks these. Change them any time from
            your profile on the pantry.
          </p>
        </header>

        <fieldset className={styles.section}>
          <legend className={styles.heading}>What do you eat?</legend>
          <div className={styles.rows}>
            {DIET_CHOICES.map((choice) => (
              <label key={choice.id} className={styles.row}>
                <input
                  type="radio"
                  name="diet"
                  className={styles.input}
                  checked={diet === choice.id}
                  onChange={() => {
                    setDiet(choice.id);
                  }}
                />
                <span className={styles.rowText}>
                  <span className={styles.rowLabel}>{choice.label}</span>
                  <span className={styles.rowHint}>{choice.hint}</span>
                </span>
                <span className={styles.dot} aria-hidden="true" />
              </label>
            ))}
          </div>
        </fieldset>

        <section className={styles.section} aria-labelledby="allergies">
          <h2 id="allergies" className={styles.heading}>
            Allergies{" "}
            <span className={styles.headingNote}>· never shown in your deck</span>
          </h2>
          <div className={styles.grid}>
            {keysOf(ALLERGENS).map((allergen) => (
              <button
                key={allergen}
                type="button"
                className={styles.pill}
                data-avoid
                aria-pressed={allergens.includes(allergen)}
                onClick={() => {
                  toggleAllergen(allergen);
                }}
              >
                {ALLERGENS[allergen]}
              </button>
            ))}
          </div>
          {allergens.includes("gluten") && (
            <p className={styles.note} role="note">
              Hing (asafoetida) isn't counted as gluten here, but many brands mix it with
              wheat flour. Use a gluten-free hing, or check its label.
            </p>
          )}

          {searching ? (
            <input
              type="search"
              className={styles.search}
              placeholder="Coconut, mushroom…"
              aria-label="Search an ingredient to avoid"
              // Opened by a tap on purpose, so typing can start at once.
              autoFocus
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
              }}
            />
          ) : (
            <button
              type="button"
              className={styles.addOther}
              onClick={() => {
                setSearching(true);
              }}
            >
              + Something else? Search any ingredient
            </button>
          )}
          {query.trim() !== "" && (
            <div className={styles.pills} aria-label="Matching ingredients" role="group">
              {matches.length === 0 && (
                <p className={styles.note}>No ingredient matches “{query.trim()}”.</p>
              )}
              {matches.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={styles.pill}
                  aria-label={`Avoid ${item.name}`}
                  onClick={() => {
                    setAvoided((list) => [...list, item.id]);
                    setQuery("");
                  }}
                >
                  + {item.name}
                </button>
              ))}
            </div>
          )}
          {avoided.length > 0 && (
            <div className={styles.pills} aria-label="Ingredients you avoid" role="group">
              {avoided.map((id) => {
                // An id the catalog no longer lists still shows, by its id.
                const name = byId.get(id)?.name ?? id;
                return (
                  <button
                    key={id}
                    type="button"
                    className={styles.avoided}
                    aria-label={`Stop avoiding ${name}`}
                    onClick={() => {
                      setAvoided((list) => list.filter((item) => item !== id));
                    }}
                  >
                    {name} <span aria-hidden="true">✕</span>
                  </button>
                );
              })}
            </div>
          )}
          <p className={styles.note}>
            Ready-made items like curry paste or stock can hide allergens, so check their
            labels too.
          </p>
        </section>
      </div>
      <div className={styles.actions}>
        <button type="button" className={styles.primary} data-kind="save" onClick={save}>
          {count === 0 ? "Save" : `Save · avoiding ${String(count)}`}
        </button>
        {firstTime && (
          <button
            type="button"
            className={styles.link}
            onClick={() => {
              markFoodRulesSeen();
              leave();
            }}
          >
            Skip for now
          </button>
        )}
      </div>
    </main>
  );
}
