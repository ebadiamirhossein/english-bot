# `apps/api` — conventions

Scaffold as of W1b: two health routes, no domain routes. What follows binds
every route added from W3 onwards.

## Layering (CLAUDE.md §2)

```
HTTP route  →  service function  →  SQL
```

A route parses, authorises, calls **one** service function, serialises. It
contains no business logic and no SQL. `tests/test_core_boundary.py`
fails the commit that puts a query in this directory.

## `def`, not `async def` — the rule that matters most here

**A route whose body reaches `llm.chat`, `speech.transcribe` or
`speech.synthesize` — directly or through a service function — must be a
plain `def`.**

`core/llm.py` and `core/speech.py` are synchronous by design: one blocking
HTTP call to a provider, no event loop anywhere in `packages/core`. FastAPI
runs a plain `def` route in a threadpool, so that blocking call costs one
thread. An `async def` route runs *on* the event loop, and a 6-second LLM
call there stalls **every** concurrent request the worker is serving — not
just the one waiting on the model.

This is known issue #7 with a wider blast radius. In v2 a 17-second blocking
LLM call inside the event loop made APScheduler skip the evening reading
poll for that tick. In an HTTP server the same mistake stalls other people's
requests.

`test_api.py::test_llm_and_speech_routes_are_plain_def` enforces it by
parsing this directory. It is in place now, while there is nothing to break.

When you genuinely need `async def` — streaming, `await`ing another async
library — the provider call still has to leave the loop:
`await asyncio.to_thread(llm.chat, ...)`, the same fix S9a applied to the
bot.

Dependencies follow the same rule: `get_db` is a plain `def` generator
because `psycopg`'s pool checkout blocks.

## CORS

`allowed_origins()` returns exactly `[WEB_ORIGIN, "http://localhost:3000"]`.
No `*`, no regex, no wildcard subdomain — the API carries a session cookie
from W2, and a credentialed wildcard hands that cookie to any origin that
asks. `WEB_ORIGIN` is empty until the domain is chosen; the phone check in
W2 is what proves it was set.

## Errors

One handler, `handle_unexpected_error`. It logs the route name and the user
id (never the request body — PRD §10), raises a throttled operator alert
through `core.services.alerts`, and returns `{"error": "internal_error"}`.
No route returns a stack trace, an exception message, or a SQL fragment.

`GET /health` is the exception to nothing: it catches its own database error
and answers **503** with `{"ok": false}`, because "the service is up, its
database is not" is a distinct fact an uptime check needs.

## Testing

Every route needs an integration test **through the ASGI transport**
(`httpx.ASGITransport`), not a direct call to the route function. v2 shipped
161 green tests over a dead feature because every one of them called the
handler directly (CLAUDE.md §3 rule 1).
