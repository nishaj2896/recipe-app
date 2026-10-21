# ADR-0006: The frontend is a mobile-first web app in this repository

- Status: Proposed
- Date: 2026-10-21
- Deciders: Nisha
- Related: ADR-0003 (cursor, deck), ADR-0005 (the API it calls)

## Context

The product is a swipe-card app: pick what's in your kitchen, get a deck of recipes, swipe right to save and left to hide. The design (Saffron Night) leans heavily on motion. Ingredients fly into a pantry jar, a cooking scene covers the search, and cards follow your finger. That motion must improve the experience, never slow it down.

v1 has no accounts, so saved and hidden recipes live on the device. The API (`/api/v1`) already returns everything a card needs: match %, matched, missing and assumed ingredients, times, diet, and a cursor for the next deck.

Three things constrain the choice:

- It has to run well on mid-range phones, at 60 fps, with the motion on.
- One person maintains it. A second codebase per platform would double the work.
- Tasks 6 to 8 put the app in containers on Kubernetes. Whatever we build has to deploy next to the API.

## Decision

**1. A mobile-first web app, installable to the home screen (a PWA).** It uses React 19, TypeScript in strict mode and Vite. A native app stays possible later, by wrapping the same code.

**2. It lives in `web/` in this repository.** API changes and the UI that uses them land in one PR, and CI checks them together.

**3. Same origin as the API, so no CORS.** In development, Vite proxies `/api` to the local server. In production, the ingress sends `/api` to the API and everything else to the static files (Tasks 6 and 7). The API stays closed to other origins.

**4. API types are generated, never written by hand.** `openapi-typescript` turns the API's OpenAPI document into `web/src/api/schema.d.ts`. CI regenerates the file and fails if it differs, so a backend change that breaks the frontend fails its own PR. Calls go through `openapi-fetch`, and TanStack Query caches them. The browser's HTTP cache honours the ETags the catalog endpoints already send.

**5. Device state lives in one versioned store.** The pantry, unticked staples, saved and hidden recipe ids, and settings are kept in `localStorage` through a small Zustand store with a schema version and a migration hook. Hidden ids keep the newest 200, the most the API accepts. A recipe id that the API no longer returns is dropped quietly.

**6. Styling uses design tokens as CSS custom properties, with CSS Modules per component.** Saffron Night is the dark theme and Fresh Market the light one, chosen by `prefers-color-scheme`. Colour carries meaning, and the meanings are fixed: green means save or have, red means skip, saffron means missing or a call to action. Text meets WCAG AA contrast in both themes.

**7. Motion uses the `motion` library and follows eight rules:**
- Never block input.
- Feedback within 100 ms, and screen changes in 200 to 350 ms.
- The search animation plays only while the request runs. It shows for at least 1.2 s and can be skipped.
- Things move to where they live.
- Springs, not fixed durations.
- Honour `prefers-reduced-motion`.
- Animate only transform and opacity.
- Haptics on every commit, and sound off by default.

**8. Ingredient art is a registry.** Each ingredient id maps to an art component, and a missing id falls back to its category's art. Swapping the style later, for example to licensed 3D renders, is a change to the registry, not to the screens.

**9. Every gesture has a button and a key.** The save, skip and undo buttons sit under the deck. The arrow keys swipe, Backspace undoes, and screen readers hear each card's name, match % and what's missing.

**10. Tests at three levels.**
- Vitest and Testing Library for components and the store.
- Playwright end-to-end tests that drive the real API and Postgres in CI.
- axe accessibility checks inside those Playwright tests.

ESLint (typescript-eslint strict), Prettier and `tsc --noEmit` run in CI next to the Python checks.

## Consequences

- **Easier:** one codebase for every phone. Each PR is reviewable in a browser. Deployment is a static bundle next to the API, and the types can't drift from the API.
- **Harder:** web gestures and haptics are less capable than native. iOS Safari has no vibration API, so haptics work on Android only. Motion has to be profiled on a real mid-range phone, not only on a laptop.
- **Risk:** heavy art or animation could miss 60 fps. The registry keeps each ingredient's art small, and the gate measures frame times.
- **Deferred:** offline support with a service worker (it comes with the home-screen install step), cooking steps and photos (the data has none yet), accounts and sync (v2).
