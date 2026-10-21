import { useState } from "react";

import type { IngredientRef, StapleKindGroup } from "../api/client";
import { Sheet } from "../app/Sheet";
import styles from "./StaplesStrip.module.css";

interface Props {
  groups: readonly StapleKindGroup[];
  outOf: readonly string[];
  onToggle: (id: string) => void;
}

const KIND_TITLE = { fresh: "Fresh staples", pantry: "Pantry staples" } as const;

/**
 * Staples are assumed (ADR-0001): the strip says so, and Edit lets the user
 * untick what they've run out of, which the search sends as excluded_staples.
 */
export function StaplesStrip({ groups, outOf, onToggle }: Props) {
  const [editing, setEditing] = useState(false);
  const staples: IngredientRef[] = groups.flatMap((group) =>
    group.categories.flatMap((category) => category.staples),
  );
  const assumed = staples.filter((staple) => !outOf.includes(staple.id));
  const missing = staples.filter((staple) => outOf.includes(staple.id));
  const named = assumed.slice(0, 3);
  const rest = assumed.length - named.length;

  return (
    <section className={styles.strip} aria-label="Staples">
      <p className={styles.text}>
        Assuming you have{" "}
        <strong>{named.map((staple) => staple.name.toLowerCase()).join(", ")}</strong>
        {rest > 0 && ` +${rest} staples`}
        {missing.length > 0 && (
          <span className={styles.out}>
            {" "}
            · out of {missing.map((staple) => staple.name.toLowerCase()).join(", ")}
          </span>
        )}
      </p>
      <button
        type="button"
        className={styles.edit}
        onClick={() => {
          setEditing(true);
        }}
      >
        Edit
      </button>
      <Sheet
        open={editing}
        title="Staples you have"
        onClose={() => {
          setEditing(false);
        }}
      >
        <p className={styles.help}>
          We assume a kitchen has these. Untick anything you've run out of.
        </p>
        {groups.map((group) => (
          <fieldset key={group.kind} className={styles.group}>
            <legend className={styles.legend}>{KIND_TITLE[group.kind]}</legend>
            {group.categories
              .flatMap((category) => category.staples)
              .map((staple) => (
                <label key={staple.id} className={styles.option}>
                  <input
                    type="checkbox"
                    checked={!outOf.includes(staple.id)}
                    onChange={() => {
                      onToggle(staple.id);
                    }}
                  />
                  {staple.name}
                </label>
              ))}
          </fieldset>
        ))}
      </Sheet>
    </section>
  );
}
