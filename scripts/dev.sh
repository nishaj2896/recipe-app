#!/usr/bin/env bash
# Runs the whole app locally with one command: starts Postgres, applies the
# migrations, syncs the data files, then serves the API on :8000 and the web
# app on :5173. Ctrl+C stops both servers; the database keeps running
# (stop it with `docker compose down`).
#
#   scripts/dev.sh            # the app on http://localhost:5173
#   scripts/dev.sh --host     # also reachable from a phone on the same Wi-Fi
#
# Extra arguments go to the web dev server (vite).
set -euo pipefail

cd "$(dirname "$0")/.."

# uv's installer puts it in ~/.local/bin, which a fresh shell may not have.
export PATH="$HOME/.local/bin:$PATH"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || fail "docker not found. Install Docker Desktop and open it."
docker info >/dev/null 2>&1 || fail "Docker isn't running. Open Docker Desktop, wait for it to start, then try again."
command -v uv >/dev/null || fail "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v npm >/dev/null || fail "npm not found. Install Node $(cat web/.nvmrc)."
node_major="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$node_major" == "$(cut -d. -f1 web/.nvmrc)" ]] \
  || fail "Node $(node --version) found, but the web app needs Node $(cat web/.nvmrc) (try: nvm use)."

if [[ ! -f .env ]]; then
  step "Creating .env with a new signing key"
  key="$(uv run --quiet python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  sed "s/REPLACE_ME/$key/" .env.example > .env
fi
set -a
# shellcheck source=/dev/null
source .env
set +a

step "Installing dependencies"
uv sync --locked --quiet
# npm ci wipes node_modules, so only run it when package-lock.json changed.
if [[ ! -f web/node_modules/.package-lock.json || web/package-lock.json -nt web/node_modules/.package-lock.json ]]; then
  (cd web && npm ci)
fi

step "Starting Postgres"
docker compose up -d --wait

step "Applying migrations"
uv run --quiet alembic upgrade head

step "Syncing data files into the database"
uv run --quiet recipe-app db sync

step "Starting the API (:8000) and the web app (:5173)"
# Job control gives each server its own process group, so the cleanup below
# stops everything they started. stdin is /dev/null so a server in the
# background never stops itself by reading the terminal.
set -m
uv run --quiet recipe-app </dev/null &
api=$!
(cd web && exec npm run dev -- "$@") </dev/null &
web=$!
set +m
trap 'kill -- "-$api" "-$web" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM

# macOS ships bash 3.2, which has no `wait -n`, so poll until either one exits.
while kill -0 "$api" 2>/dev/null && kill -0 "$web" 2>/dev/null; do
  sleep 1
done
fail "a server stopped (see above), so the other one was stopped too."
