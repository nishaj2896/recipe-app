import { act, fireEvent, render, screen } from "@testing-library/react";
import { domMax, LazyMotion } from "motion/react";
import { createRef } from "react";

import { SwipeCard, type SwipeCardHandle } from "./SwipeCard";

function renderCard() {
  const ref = createRef<SwipeCardHandle>();
  const onSwipe = vi.fn();
  const onGone = vi.fn();
  const onOpen = vi.fn();
  const view = render(
    <LazyMotion features={domMax} strict>
      <SwipeCard
        ref={ref}
        label="Aloo matar"
        onSwipe={onSwipe}
        onGone={onGone}
        onOpen={onOpen}
      >
        Aloo matar
      </SwipeCard>
    </LazyMotion>,
  );
  return { ...view, ref, onSwipe, onGone, onOpen };
}

test("a card that unmounts mid-flight is reported gone once", async () => {
  const { ref, onSwipe, onGone, unmount } = renderCard();

  act(() => {
    ref.current?.fling("right");
  });
  expect(onSwipe).toHaveBeenCalledWith("right");
  expect(onGone).not.toHaveBeenCalled();

  // New filters deal a new deck while the card is still in the air.
  unmount();
  expect(onGone).toHaveBeenCalledTimes(1);

  // The stopped flight doesn't report it again later.
  await new Promise((resolve) => setTimeout(resolve, 1500));
  expect(onGone).toHaveBeenCalledTimes(1);
});

test("a card that never left isn't reported gone when it unmounts", () => {
  const { onGone, unmount } = renderCard();
  unmount();
  expect(onGone).not.toHaveBeenCalled();
});

test("a tap opens the recipe, but not once the card is leaving", () => {
  const { ref, onOpen } = renderCard();
  const card = screen.getByRole("article", { name: "Aloo matar" });

  fireEvent.pointerDown(card);
  fireEvent.click(card);
  expect(onOpen).toHaveBeenCalledTimes(1);

  act(() => {
    ref.current?.fling("left");
  });
  fireEvent.click(card);
  expect(onOpen).toHaveBeenCalledTimes(1);
});
