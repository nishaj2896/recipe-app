import { useState } from "react";

import { DishArt } from "./IngredientArt";

interface Props {
  recipeId: string;
  url: string;
  alt: string;
  className: string | undefined;
  /** The drawn bowl's size, if the file doesn't load. */
  artSize: number;
}

/** The dish's photo; the drawn bowl stands in if the file doesn't load. */
export function DishPhoto({ recipeId, url, alt, className, artSize }: Props) {
  const [failed, setFailed] = useState(false);
  if (failed) return <DishArt recipeId={recipeId} size={artSize} />;
  return (
    <img
      className={className}
      src={url}
      alt={alt}
      width={800}
      height={800}
      decoding="async"
      draggable={false}
      onError={() => {
        setFailed(true);
      }}
    />
  );
}
