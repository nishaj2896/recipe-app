import styles from "./PantryScreen.module.css";

/** The first screen: pick what's in your kitchen. Filled in by the next PR. */
export function PantryScreen() {
  return (
    <main className={styles.screen}>
      <h1 className={styles.title}>What's in your kitchen?</h1>
      <p className={styles.lede}>
        Tap what you have and we'll find recipes you can cook.
      </p>
    </main>
  );
}
