import { Component, type ReactNode } from "react";

import styles from "./ScreenError.module.css";

interface Props {
  children: ReactNode;
}

/**
 * Catches a screen that fails to load or render, so the rest of the app
 * stays up. A screen's code is fetched when it's first opened (issue #52):
 * a dropped connection, or a deploy that renamed the files while the app was
 * open, fails that fetch. Reloading recovers from both.
 */
export class ScreenError extends Component<Props, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className={styles.screen}>
        <div role="alert" className={styles.message}>
          <h1 className={styles.title}>Couldn't load this screen</h1>
          <p className={styles.muted}>Check your connection, then try again.</p>
          <button
            type="button"
            className={styles.retry}
            onClick={() => {
              window.location.reload();
            }}
          >
            Try again
          </button>
        </div>
      </main>
    );
  }
}
