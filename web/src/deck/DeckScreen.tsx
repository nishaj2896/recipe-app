import { Link } from "react-router";

import styles from "./DeckScreen.module.css";

/** Placeholder until the deck lands in the next PR. */
export function DeckScreen() {
  return (
    <main className={styles.screen}>
      <h1 className={styles.title}>Your recipes are next</h1>
      <p className={styles.text}>The swipe deck arrives in the next update.</p>
      <Link to="/" className={styles.back}>
        Back to your pantry
      </Link>
    </main>
  );
}
