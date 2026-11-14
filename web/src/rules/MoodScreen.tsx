import { useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { BackArrow } from "../app/BackArrow";
import { useLeave } from "../app/leave";
import { type MoodPicks, noMood, useDevice } from "../store/device";
import styles from "./Choices.module.css";
import { COURSES, keysOf, MOODS, TIME_CHOICES, TIMES, WEATHER } from "./labels";
import { pickedCount } from "./summary";

/** Set by the deck's mood chip, so a new deal replaces the mood screen. */
export interface MoodScreenState {
  fromDeck?: boolean;
}

/**
 * The short screen before the deck (ADR-0012 rules 5 and 12): what you're
 * making, how long you have and, under "Fine-tune", mood and weather. Every
 * part is optional, and it opens with the last picks.
 */
export function MoodScreen() {
  const hydration = useDevice((state) => state.hydration);
  return hydration === "pending" ? null : <MoodForm />;
}

function MoodForm() {
  const navigate = useNavigate();
  const location = useLocation();
  const leave = useLeave();
  const { setMood } = useDevice.getState();
  const [picks, setPicks] = useState<MoodPicks>(useDevice.getState().mood);
  const [fineTune, setFineTune] = useState(
    picks.moods.length > 0 || picks.weather.length > 0,
  );
  const picked = pickedCount(picks);
  const fineTuned = [
    ...picks.moods.map((mood) => MOODS[mood]),
    ...picks.weather.map((weather) => WEATHER[weather]),
  ];

  function toggle<K extends "courses" | "moods" | "weather">(
    key: K,
    value: MoodPicks[K][number],
  ) {
    setPicks((current) => {
      const list = current[key] as readonly string[];
      return {
        ...current,
        [key]: list.includes(value)
          ? list.filter((item) => item !== value)
          : [...list, value],
      };
    });
  }

  function deal(mood: MoodPicks) {
    setMood(mood);
    const fromDeck = (location.state as MoodScreenState | null)?.fromDeck === true;
    void navigate("/deck", { replace: fromDeck });
  }

  return (
    <main className={styles.screen}>
      <div className={styles.body}>
        <div className={styles.top}>
          <button type="button" className={styles.back} aria-label="Back" onClick={leave}>
            <BackArrow />
          </button>
          <p className={styles.eyebrow}>All optional · skip any</p>
        </div>

        <section className={styles.section} aria-labelledby="courses">
          <h1 id="courses" className={styles.title}>
            What are you making?
          </h1>
          <div className={styles.pills}>
            {keysOf(COURSES).map((course) => (
              <button
                key={course}
                type="button"
                className={styles.pill}
                aria-pressed={picks.courses.includes(course)}
                onClick={() => {
                  toggle("courses", course);
                }}
              >
                {COURSES[course]}
              </button>
            ))}
          </div>
        </section>

        <fieldset className={styles.section}>
          <legend className={styles.heading}>How long have you got?</legend>
          <div className={styles.segments}>
            {TIME_CHOICES.map((time) => (
              <label key={time} className={styles.segment}>
                <input
                  type="radio"
                  name="time"
                  className={styles.input}
                  checked={picks.time === time}
                  onChange={() => {
                    setPicks((current) => ({ ...current, time }));
                  }}
                />
                {TIMES[time]}
              </label>
            ))}
          </div>
          <p className={styles.note}>
            Hands-on time. Soaking and marinating don't count, and those recipes show a
            plan-ahead label.
          </p>
        </fieldset>

        <button
          type="button"
          className={styles.fineTune}
          aria-expanded={fineTune}
          aria-controls="fine-tune"
          onClick={() => {
            setFineTune((open) => !open);
          }}
        >
          <span className={styles.fineTuneText}>
            <span className={styles.fineTuneLabel}>Fine-tune</span>
            <span className={styles.note}>
              {fineTuned.length > 0
                ? `${String(fineTuned.length)} picked · ${fineTuned.join(", ")}`
                : "Mood and weather, if you like"}
            </span>
          </span>
          <span className={styles.fineTuneArrow} aria-hidden="true">
            {fineTune ? "−" : "+"}
          </span>
        </button>

        <div id="fine-tune" hidden={!fineTune} className={styles.section}>
          <section className={styles.section} aria-labelledby="moods">
            <h2 id="moods" className={styles.heading}>
              In the mood for…
            </h2>
            <div className={styles.pills}>
              {keysOf(MOODS).map((mood) => (
                <button
                  key={mood}
                  type="button"
                  className={styles.pill}
                  aria-pressed={picks.moods.includes(mood)}
                  onClick={() => {
                    toggle("moods", mood);
                  }}
                >
                  {MOODS[mood]}
                </button>
              ))}
            </div>
          </section>
          <section className={styles.section} aria-labelledby="weather">
            <h2 id="weather" className={styles.heading}>
              How's the weather making you feel?
            </h2>
            <div className={styles.pills}>
              {keysOf(WEATHER).map((weather) => (
                <button
                  key={weather}
                  type="button"
                  className={styles.pill}
                  aria-pressed={picks.weather.includes(weather)}
                  onClick={() => {
                    toggle("weather", weather);
                  }}
                >
                  {WEATHER[weather]}
                </button>
              ))}
            </div>
            <p className={styles.note}>
              Weather never hides a recipe: it brings the ones that suit it forward.
            </p>
          </section>
        </div>
      </div>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primary}
          onClick={() => {
            deal(picks);
          }}
        >
          {picked === 0 ? "Deal my cards" : `Deal my cards · ${String(picked)} picked`}
        </button>
        {picked > 0 && (
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              deal(noMood);
            }}
          >
            Show me everything
          </button>
        )}
      </div>
    </main>
  );
}
