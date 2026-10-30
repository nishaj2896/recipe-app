# ADR-0011: Dish photos stay in Git

- Status: Accepted
- Date: 2026-10-30
- Deciders: Nisha
- Amends: ADR-0008 risk "before the photos pass 100, a follow-up ADR decides between Git LFS and object storage"
- Related: ADR-0010 (the card carries the photo)

## Context

ADR-0008 asked for a decision on Git LFS or object storage before the photos passed 100. They are about to pass 100, and Nisha plans about 1,000 photos, possibly more later. Each photo is an 800 × 800 WebP of up to 150 KB, about 110 KB in practice.

## Decision

**1. Photos stay in the repository, under `web/public/dishes/`.** No Git LFS and no object storage for now. The repository is public, so GitHub charges nothing for it. 1,000 photos are about 110 MB; with regenerated photos left in history, plan for 150 to 250 MB, under GitHub's recommended 1 GB. Git LFS would add a paid quota and CI and Docker setup, and a bucket would add infrastructure that nothing else needs yet.

**2. Revisit when the repository passes about 500 MB, or with the Docker and Kubernetes tasks.** The `/dishes/` URL is the same either way, so moving the files to a bucket behind a CDN later changes the deploy, not the app. That move needs its own ADR.

## Consequences

- **Easier:** nothing new to set up; photos are reviewed and merged like any other change.
- **Harder:** history never shrinks. Each regenerated photo stays as an old copy, and the Docker image grows by the size of the photos.
- **Deferred:** a bucket and CDN, and a thumbnail size for cards.
