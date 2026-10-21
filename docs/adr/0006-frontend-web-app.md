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

**1. A mobile-first web app, installable to the home screen.** It uses React 19, TypeScript in strict mode and Vite, with Node 22 LTS and npm (`package-lock.json`, `npm ci`). v1 ships a web app manifest, which is enough for Add to Home Screen on iOS and for Chrome's install prompt. Offline support is deferred (see Consequences). A native app stays possible later, by wrapping the same code.

**2. It lives in `web/` in this repository.** API changes and the UI that uses them land in one PR, and CI checks them together.

**3. Same origin as the API, so no CORS.** In development, Vite proxies `/api` to the local server. In production, the ingress sends `/api` to the API and everything else to the static files (Tasks 6 and 7). The API stays closed to other origins. A native wrapper would serve from its own origin and need a narrow CORS allow-list, decided then. Serving from one origin also lets the static app ship a strict Content-Security-Policy (no inline script, `connect-src 'self'`). Task 7 sets the header.

**4. API types are generated, never written by hand.** `recipe-app openapi` prints the API's OpenAPI document without a database or settings, and it is committed as `web/openapi.json`, so every contract change shows up as a readable diff. `openapi-typescript` turns it into `web/src/api/schema.d.ts`. CI regenerates both files and fails if either differs, so a backend change that breaks the frontend fails its own PR. Calls go through `openapi-fetch`, and TanStack Query caches them. The browser's HTTP cache honours the ETags the catalog endpoints already send.

**5. Device state lives in one versioned store, and saved recipes are never lost by accident.** In v1 the device holds the only copy of what a user saved.
- The pantry, unticked staples, saved and hidden recipe ids, and settings live in IndexedDB, through a small Zustand store with a schema version and a migration hook. IndexedDB is asynchronous, so a write never blocks a swipe, and it has a far larger quota than `localStorage`.
- After the first save, the app asks for persistent storage (`navigator.storage.persist()`) and suggests installing to the home screen. Installed apps are exempt from Safari's 7-day eviction.
- **A saved or hidden id is never dropped because the API returns 404.** Recipes are never deleted (ADR-0001 rule 2, ADR-0005 rule 2), but a pod can return 404 for a real recipe between a sync and its restart (ADR-0005, Risk). The card shows as "unavailable right now" and the app retries on the next launch. Pruning would need an explicit signal from the API, never an absence.
- Hidden ids keep the newest 200, the most the API accepts. The 201st hide lets the oldest hidden recipe back into decks, which is an accepted trade-off.
- Pantry ids the search reports under `ignored_ingredients` (retired, or now a staple) are removed from the pantry, and the user is told which ones.

**6. Styling uses design tokens as CSS custom properties, with CSS Modules per component.** Saffron Night is the dark theme and Fresh Market the light one, chosen by `prefers-color-scheme`. Colour carries meaning, and the meanings are fixed: green means save or have, red means skip, saffron means missing or a call to action. Text meets WCAG AA contrast in both themes.

**7. Motion uses the `motion` library and follows eight rules:**
- Never block input.
- Feedback within 100 ms, and screen changes in 200 to 350 ms.
- The search animation plays on every search as a brand moment, for about 1.2 s even when the API answers faster (most searches take about 50 ms), and a tap skips it. This is a deliberate trade: roughly a second per search for a consistent signature moment. If the request outlasts it, it keeps playing until the results arrive. With reduced motion on, a short fade replaces it.
- Things move to where they live.
- Springs, not fixed durations.
- Honour `prefers-reduced-motion`.
- Animate only transform and opacity.
- Haptics on every committed swipe or button press, and sound off by default.

**8. Ingredient art is a registry of drawn 3D-style icons.** Glossy SVG icons are drawn in code, in the style of the mockups. About 40 common ingredients get their own icon, and every other ingredient falls back to its category's icon. Each ingredient id maps to an art component in the registry. Swapping the style later, for example to licensed 3D renders, is a change to the registry, not to the screens.

**9. Every gesture has a button and a key.** The save, skip and undo buttons sit under the deck. While the deck has focus, the arrow keys swipe and Backspace undoes. They never fire while someone is typing in the pantry search. Screen readers hear each card's name, match % and what's missing, and are told when a swipe is undone.

**10. Tests at three levels.**
- Vitest and Testing Library for components and the store.
- Playwright end-to-end tests that drive the real API and Postgres in CI.
- axe accessibility checks inside those Playwright tests.
- A motion budget: Playwright replays the ingredient flight, a swipe and the deck deal with the CPU throttled to 4×. It fails on any long task over 50 ms, recorded by the browser's `longtask` performance observer. Before each release, the app is also profiled by hand on a real mid-range Android phone.

ESLint (typescript-eslint strict), Prettier and `tsc --noEmit` run in CI next to the Python checks.

## Consequences

- **Easier:** one codebase for every phone. Each PR is reviewable in a browser. Deployment is a static bundle next to the API, and the types can't drift from the API.
- **Harder:** web gestures and haptics are less capable than native. iOS Safari has no vibration API, so haptics work on Android only. Motion has to be profiled on a real mid-range phone, not only on a laptop.
- **Risk:** heavy art or animation could miss 60 fps. The registry keeps each ingredient's art small, and the motion budget in rule 10 fails CI on long tasks.
- **Risk:** browsers can evict a site's storage. Safari clears it after 7 days without a visit unless the app is installed, and other browsers evict under storage pressure. Rule 5's persistent-storage request and the install nudge are the mitigations. Accounts and sync in v2 remove the risk.
- **Deferred:** offline support with a service worker, cooking steps and photos (the data has none yet), accounts and sync (v2).
