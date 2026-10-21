import { useState } from "react";

import type { Diet } from "../store/device";
import styles from "./FilterSheet.module.css";
import { DIET_OPTIONS, TIME_OPTIONS, timeLabel } from "./filters";

export interface Filters {
  diet: Diet | null;
  maxTotalMinutes: number | null;
}

interface Props {
  initial: Filters;
  /** Deals a fresh deck with these filters. */
  onApply: (filters: Filters) => void;
}

/**
 * The deck's diet and time filters. Nothing changes until "Show recipes", so
 * closing the sheet keeps the deck the user is on.
 */
export function FilterSheet({ initial, onApply }: Props) {
  const [diet, setDiet] = useState(initial.diet);
  const [maxTotalMinutes, setMaxTotalMinutes] = useState(initial.maxTotalMinutes);
  const changed = diet !== initial.diet || maxTotalMinutes !== initial.maxTotalMinutes;

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        onApply({ diet, maxTotalMinutes });
      }}
    >
      <fieldset className={styles.group}>
        <legend className={styles.legend}>Diet</legend>
        <div className={styles.options}>
          {DIET_OPTIONS.map((option) => (
            <label key={option.label} className={styles.option}>
              <input
                type="radio"
                name="diet"
                className={styles.radio}
                checked={diet === option.value}
                onChange={() => {
                  setDiet(option.value);
                }}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className={styles.group}>
        <legend className={styles.legend}>Ready in</legend>
        <div className={styles.options}>
          {TIME_OPTIONS.map((minutes) => (
            <label key={String(minutes)} className={styles.option}>
              <input
                type="radio"
                name="time"
                className={styles.radio}
                checked={maxTotalMinutes === minutes}
                onChange={() => {
                  setMaxTotalMinutes(minutes);
                }}
              />
              {timeLabel(minutes)}
            </label>
          ))}
        </div>
      </fieldset>
      <button type="submit" className={styles.apply} disabled={!changed}>
        Show recipes
      </button>
    </form>
  );
}
