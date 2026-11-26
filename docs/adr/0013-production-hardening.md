# ADR-0013: Production hardening

- Status: Accepted
- Date: 2026-11-26
- Deciders: Nisha
- Related: ADR-0005 rule 7 (the app still refuses to start on a bad setting), issues #30 (item 3), #37, #47

## Context

Task 4 of the roadmap asks for an API that fails cleanly. Its gate: kill the database mid-request, and the API answers a clean 503 quickly, not a stack trace or a hang.

On `main` as of 12ff2db (after #125, which turned the API docs off and added the security headers):

- Nothing in the path to Postgres has a time limit. asyncpg waits 60 s to connect, a checkout waits 30 s for a free pooled connection, and a query can run, or wait on a dead network, forever.
- A database failure reaches the catch-all handler. The body is a clean, generic 500 (nothing leaks), but 500 tells the client and the monitoring that the code is broken, and nothing says when to retry.
- Logs are plain text, uvicorn's access log is a second plain format, and no line can be tied to the request that caused it.
- On SIGTERM, uvicorn waits for in-flight requests with no upper limit.
- `jit = off` is sent as a connection startup parameter, which PgBouncer rejects (#37).
- Settings are read by hand-written functions, one per variable.

Input limits (ADR-0003, the 64 KiB body cap) and the no-leak error bodies are already in place and stay as they are.

## Decision

**1. A failure of the database, or of our own capacity, is a 503 problem with `Retry-After: 2`.** The type is `/problems/service-unavailable`, the title `Service Unavailable`, and the detail a fixed sentence that names no cause. These failures count:

| Cause | How it shows up |
| --- | --- |
| Can't connect, or the connection drops mid-query | A connect `TimeoutError` or `OSError`, or SQLAlchemy's `OperationalError` / `InterfaceError` wrapping asyncpg's connection errors (the connection is then marked invalidated) |
| A statement ran past its budget | SQLSTATE `57014` (`query_canceled`) from Postgres, or asyncpg's client-side timeout |
| No pooled connection was free in time | `sqlalchemy.exc.TimeoutError` |
| The whole request ran past its deadline (rule 7) | our deadline middleware |
| Too many requests already in flight (rule 7) | our concurrency limit |

Anything else is still the generic 500. A 504 is left to gateways, so a 504 always means the ingress gave up, never the app.

The mapping lives at the infrastructure boundary: the Postgres adapter turns these errors into one `DatabaseUnavailableError`, and only that error (with the deadline and concurrency cases) becomes a 503. A `TimeoutError` or `OSError` raised anywhere else is a bug, and stays a 500.

`Retry-After: 2` is advice, not a schedule. The web app never retries on its own: a person presses "Try again" (rule 11), so the API's own clients can't pile on during an outage. If a client that retries by itself ever arrives, it must add jitter and back off, and the value is a setting so it can grow without a release.

**2. Every wait has a budget, and each budget sits inside the next.** All are settings, with these defaults:

| Setting | Default | What it bounds |
| --- | --- | --- |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | 3 | Opening a new connection (asyncpg `timeout`) |
| `DATABASE_POOL_TIMEOUT_SECONDS` | 2 | Waiting for a free pooled connection |
| `DATABASE_STATEMENT_TIMEOUT_SECONDS` | 3 | One statement, enforced by Postgres (`statement_timeout`) |
| (derived: statement + 1) | 4 | One statement, enforced by the client (asyncpg `command_timeout`) |
| `REQUEST_TIMEOUT_SECONDS` | 8 | The whole request, from first byte in to response |

The request deadline is the only end-to-end bound. The others bound one step each: a request makes up to three statements, so the steps can add up to more than 8 s, and the deadline cuts it off at 8 s. The statement budget is 15 times the search's 200 ms p95 budget in CI, so a healthy query never meets it. Two statement timeouts are needed because they cover different failures. The server's timeout frees Postgres from a runaway query. The client's timeout frees the API when the network is dead: a blackholed connection never delivers the server's cancel, so without it the request would wait until the deadline.

**3. Session settings are applied per transaction with `SET LOCAL`.** At the start of every transaction the engine runs `SET LOCAL statement_timeout = ...` and `SET LOCAL jit = off`. `SET LOCAL` ends with the transaction, so it is correct behind any pooler, including PgBouncer in transaction mode (#37), and it costs one round trip of well under a millisecond. The `server_settings` startup parameter is removed.

**4. Logs are JSON lines on stdout, through the standard `logging` module.** No new dependency: a formatter of about 60 lines turns each record into one JSON object with `time` (UTC, ISO 8601), `level`, `logger`, `message` and `request_id`, plus `exc_type` and the traceback for errors. uvicorn's and SQLAlchemy's loggers go through the same handler. `LOG_FORMAT=text` keeps readable lines for local development, and `LOG_LEVEL` defaults to `INFO`.

The app writes one access line per request, at INFO, with `method`, `route` (the template, such as `/api/v1/recipes/{recipe_id}`, so ids don't multiply the distinct values; a path that matches no route logs `unmatched`, never the raw path), `status` and `duration_ms`. uvicorn's own access log is turned off. **Never logged:** request or response bodies, query strings, SQL text or parameters, header values other than the request ID, and any setting marked secret.

**5. Every request has an ID.** An incoming `X-Request-ID` matching `^[A-Za-z0-9_-]{8,64}$` is kept, so an ingress can stamp one ID from the edge to the pod. Any other value, or none, is replaced by a new UUIDv7. The pattern rules out spaces, quotes and newlines, so a client can't forge log lines through it. The ID is held in a `contextvar`, so every log line written during the request carries it. It goes back in the `X-Request-ID` response header and as `request_id` in every 5xx problem body, so a screenshot of an error is enough to find its log lines.

**6. One uvicorn process per container, with a pool of 5 plus 5 overflow.** Scaling means more pods, not more workers: Kubernetes already restarts, spreads and balances processes. Each pod then holds at most 10 connections, so 8 pods fit Postgres's default `max_connections` of 100 with room for migrations and an admin session. `pool_pre_ping` stays on, which costs one round trip per checkout and keeps a connection killed by a database restart from failing a request. `DATABASE_POOL_SIZE` and `DATABASE_POOL_MAX_OVERFLOW` are settings.

**7. Requests have a deadline and a concurrency limit, and shutdown is bounded.**

- **Pure ASGI middleware.** The deadline, the concurrency limit, the request ID and the access log are plain ASGI middleware, not Starlette's `BaseHTTPMiddleware`, which runs the app in a separate task and gets cancellation and streaming wrong.
- **Deadline.** The middleware runs the request under `asyncio.timeout(REQUEST_TIMEOUT_SECONDS)`. When it fires, the work is cancelled and the client gets rule 1's 503, but only if no part of the response has been sent yet. Once the headers are out, the connection is closed instead and the access line records the cut. A query cancelled this way leaves its connection in an unknown state, so the pool discards it rather than reuse it, and the chaos test (rule 10) checks that the next request on the same pool succeeds.
- **Concurrency limit.** At most `MAX_IN_FLIGHT_REQUESTS` (default 64) requests per process run at once. One more gets rule 1's 503 at once, instead of queueing until every request is slow. This is our own middleware, not uvicorn's `--limit-concurrency`, which answers in plain text rather than a problem.
- **Liveness is exempt.** `/healthz` skips both, so a busy pod is never killed for being busy.
- **Shutdown.** After SIGTERM, uvicorn stops accepting connections and lets in-flight requests finish for at most `SHUTDOWN_GRACE_SECONDS` (default 20), then exits and closes the pool. Kubernetes kills at 30 s by default, which leaves 10 s of margin. Taking the pod out of the load balancer first comes with readiness probes (Tasks 5 and 9).
- **One entry point.** `recipe-app serve` starts uvicorn with all of these from `Settings`. The Dockerfile's `CMD` uses it, so no limit lives in CLI flags.

**8. Settings are one `pydantic-settings` object, read once at startup.** This adds `pydantic-settings` (and its `python-dotenv` dependency, which stays unused: no `.env` file is read) as a runtime dependency. The variable names in use stay. `DATABASE_URL` and `CURSOR_SIGNING_KEYS` are `SecretStr`, so printing the settings shows `**********`. Any missing or invalid value stops the app before it binds a port, with a message that names the variable but never echoes its value (ADR-0005 rule 7). At startup the app logs every setting with secrets hidden.

**9. Migrations fail fast on a lock.** `migrations/env.py` sets `lock_timeout = '5s'` and `statement_timeout = '5min'` (#30 item 3). Without a lock timeout, an `ALTER TABLE` waiting behind a long read holds its place in the lock queue, and every query after it waits too. That stalls all traffic while the migration waits.

**10. The gate is a chaos test in CI.** Tests in `tests/chaos/` put a small asyncio TCP proxy between the API and Postgres, which can reset, freeze or refuse connections on cue. They cover the database killed mid-request, a frozen network, the deadline firing mid-query with the pool reused afterwards, the database down before a request, an exhausted pool, recovery without a restart, and SIGTERM during a request. Each test checks the status code, the time taken, the body (no traceback, `request_id` present) and the log (one WARNING naming the cause, no SQL). The catalog routes `/api/v1/ingredients` and `/api/v1/staples` are served from memory, so they keep answering 200 while the database is down.

**11. The deck tells a 503 apart from other errors** (#47, first half). It says "The kitchen is busy. Try again in a moment." and keeps "Try again" disabled for the `Retry-After` seconds. The unknown-ingredient half of #47 waits for its own problem type.

## Consequences

- **Easier:** every failure has a bounded time, a status that says whether retrying helps, and one log line with a request ID. The settings and limits needed for Kubernetes (Tasks 8 and 9) already exist.
- **Harder:** a slow but valid request over 8 s now fails. No request is anywhere near that today, but a future feature that needs longer has to raise the budget on purpose. Each transaction costs one more round trip for `SET LOCAL`.
- **Watch in production:** the 503 rate split by cause (statement timeout means a slow query or a lock; pool timeout means too few connections; connect means the database or network is down), and pods × 10 against `max_connections`.
- **Deferred:** metrics, traces and readiness (Task 5); pinning Postgres by digest and testing version 16 in CI (#30 items 1 and 2, Tasks 6 and 7); a connection pooler, if pods outgrow `max_connections` (Task 9).
