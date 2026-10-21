import type { CatalogIngredient } from "../api/client";
import { Sheet } from "../app/Sheet";
import { IngredientArt } from "../art/IngredientArt";
import styles from "./PantrySheet.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  items: readonly CatalogIngredient[];
  onRemove: (id: string) => void;
  onClear: () => void;
}

export function PantrySheet({ open, onClose, items, onRemove, onClear }: Props) {
  return (
    <Sheet open={open} onClose={onClose} title="Your pantry">
      {items.length === 0 ? (
        <p className={styles.empty}>Nothing yet. Tap an ingredient to add it.</p>
      ) : (
        <>
          <ul className={styles.list}>
            {items.map((item) => (
              <li key={item.id} className={styles.item}>
                <IngredientArt
                  ingredientId={item.id}
                  categoryId={item.category.id}
                  size={36}
                />
                <span className={styles.name}>{item.name}</span>
                <button
                  type="button"
                  className={styles.remove}
                  aria-label={`Remove ${item.name}`}
                  onClick={() => {
                    onRemove(item.id);
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className={styles.clear} onClick={onClear}>
            Clear pantry
          </button>
        </>
      )}
    </Sheet>
  );
}
