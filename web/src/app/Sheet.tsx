import { useEffect, useRef, type ReactNode } from "react";

import styles from "./Sheet.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/**
 * A bottom sheet on the native <dialog>, which brings focus trapping, Escape
 * to close and an inert page behind it for free.
 */
export function Sheet({ open, onClose, title, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={styles.sheet}
      aria-label={title}
      onClose={onClose}
      onClick={(event) => {
        // A click on the backdrop lands on the dialog itself.
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className={styles.body}>
        <header className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button type="button" className={styles.done} onClick={onClose}>
            Done
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}
