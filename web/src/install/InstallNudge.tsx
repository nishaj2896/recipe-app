import { useDevice } from "../store/device";
import { promptInstall, useInstallWay } from "./install";
import styles from "./InstallNudge.module.css";

/**
 * After the first save: saved recipes live only on this phone, and an
 * installed app keeps its storage (Safari clears a site's after 7 days without
 * a visit). ADR-0006 rule 5.
 */
export function InstallNudge() {
  const way = useInstallWay();
  const saved = useDevice((state) => state.saved.length);
  const dismissed = useDevice((state) => state.installNudgeDismissed);
  const dismiss = useDevice((state) => state.dismissInstallNudge);

  if (!way || saved === 0 || dismissed) return null;

  return (
    <aside className={styles.nudge} aria-label="Add to home screen">
      <img
        className={styles.icon}
        src="/icons/icon-192.png"
        alt=""
        width={44}
        height={44}
      />
      <div className={styles.text}>
        <p className={styles.title}>Keep your recipes on your home screen</p>
        <p className={styles.body}>
          Install the app so your saves stay put and it opens like any other app.
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.install}
            onClick={() => {
              void promptInstall();
            }}
          >
            Install
          </button>
          <button type="button" className={styles.later} onClick={dismiss}>
            Not now
          </button>
        </div>
      </div>
    </aside>
  );
}
