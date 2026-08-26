# Cloudflare Workers Free-tier runbook

Operational reference for `fanfic-web` on Cloudflare Workers Free — what to
do when something looks wrong, without guessing. Companion to
[`cloudflare-quota-incident-2026-08-26.md`](cloudflare-quota-incident-2026-08-26.md),
which documents the one incident that prompted this runbook to exist.

## How to recognize the failure mode

**Error 1027** ("Sorry, you have been blocked... the owner of this website
has reached their plan limits") served by Cloudflare itself (not the app) on
literally every request, from every visitor, with no cookies/session
involved — confirmed by a plain `curl` with no browser state. This is the
Workers Free plan's **100,000 requests/day** ceiling, reached and not yet
reset. It is a whole-zone outage, not a per-visitor block, and not caused by
anything wrong with the deployed code's correctness (the code can be
perfectly fine and still hit 1027 if something calls it too often).

Distinguish this from:
- **Error 1102 / "Worker exceeded resource limits"** — a single request's
  CPU/memory budget, not the daily count. Different problem, different fix
  (already solved earlier by `enableCacheInterception` — see
  `web/open-next.config.ts`).
- **A normal 5xx from the backend** (`fas-prod-api.onrender.com`) — that's
  Render, not Cloudflare; 1027 is a Cloudflare-branded error page, a 502/504
  from the app is not.

## Immediate response

1. **Stop generating more traffic against the zone.** Don't repeatedly poll
   it "to see if it's back" — every poll (curl or browser) is itself a
   request against the same exhausted counter, and doesn't get answered any
   faster by asking more often.
2. **Do not deploy new code as a fix for 1027 by itself.** A deploy changes
   the Worker's *code*, not the *request counter* — it doesn't reset the
   quota. Only deploy if the traffic pattern itself needs fixing (see the
   2026-08-26 incident for an example: an actual runaway client-side loop).
3. **Check the dashboard** (see below) to see the actual request curve —
   confirm this is genuinely quota exhaustion and not something else wearing
   the same symptom.
4. **Wait for the daily reset** (00:00 UTC) if the cause is a one-time spike
   that has already stopped. If the cause is still *active* (an ongoing
   loop, a bot, a bad deploy still live), fix that first — waiting for reset
   without fixing the cause just delays the next 1027 by one day.

## What NOT to do

- **Do not upgrade to Cloudflare Workers Paid** as a reflexive fix. The paid
  plan raises the ceiling, it doesn't address *why* the ceiling was hit — if
  the cause is a bug (as it was on 2026-08-26: an unbounded prefetch loop),
  paying more just means the same bug burns real money instead of failing
  loudly and for free. Fix the traffic pattern first; revisit plan tier only
  if genuine, legitimate traffic outgrows the free ceiling.
- **Do not disable prefetching wholesale** on genuinely dynamic, per-item
  routes (chapters, novels, animation episodes) to "be safe." Those already
  prefetch correctly (once, on real hover/viewport intent) and disabling
  them trades a real Cloudflare-quota risk for a real degraded-UX cost, for
  no benefit — see the link-classification audit for which routes actually
  needed `prefetch={false}` and why.
- **Do not add authentication, IP-blocking, or bot-mitigation** as a
  response to 1027 unless the dashboard curve actually shows external
  abuse (see below) — the 2026-08-26 incident's entire cause was internal
  (this app's own client code), and defenses aimed at outside attackers
  would have done nothing for it.

## How to inspect the Worker's request count

**Right now, zero setup:** Cloudflare Dashboard → **Workers & Pages** →
`fanfic-web` → **Metrics** tab. Shows requests, errors, CPU time, and
sub-requests over 24h/7d/30d, already available on the Free plan.

**Automatable (needs a one-time token, see below):** the GraphQL Analytics
API (`workersInvocationsAdaptive` dataset) — query template and setup steps
in `cloudflare-quota-incident-2026-08-26.md`'s "Monitoring" section. Not
implemented as a running script yet; that report documents the exact path
without inventing credentials.

## Diagnosing a prefetch/request storm specifically

The 2026-08-26 incident's signature, useful for recognizing a repeat:

1. Open the site in a browser, open DevTools → Network, filter by `Fetch/XHR`
   or by the `_rsc` query param Next.js appends to prefetch requests.
2. Load a page and then **do nothing** — don't click, don't scroll.
3. **Expected (healthy):** the request list goes quiet within a second or
   two of the initial load. A handful of one-time prefetches for
   in-viewport dynamic links is normal; it should stop, not repeat.
4. **Storm signature:** the SAME request (same URL) repeats every few tens
   of milliseconds, forever, regardless of a `200`/`x-nextjs-stale-time`
   response. If you see this, the offending `<Link>` almost certainly needs
   `prefetch={false}` — see `web/tests/static-link-prefetch.test.mjs` for
   the standing regression test that should have caught it, and check
   whether a *new* static-destination link was added without that prop.

## Deployment verification

After any frontend deploy, for the first 10-15 minutes:
1. Check the Metrics tab request curve — it should look like normal traffic
   (proportional to real visits), not a step-change spike.
2. Do the idle-network check above on the deployed URL, once, briefly — not
   a repeated polling loop.
3. If a spike appears, treat it as a potential regression of the same class
   of bug fixed on 2026-08-26 (a link/effect that reintroduced continuous
   requests) before assuming it's just "more traffic."

## Reset behavior

Daily quota resets at **00:00 UTC**. It is a hard reset of the counter, not
a rolling 24h window — traffic from 23:59 UTC and 00:01 UTC count against
two different days' budgets even though only two minutes apart. This means
a burst right before midnight UTC and a second burst right after can both
independently trigger 1027 on their respective days even if the combined
rate looks the same either side of the boundary.

## Interpreting the request budget

See the [free-tier hardening audit](overnight-2026-08-27-technical-audit.md)
for the worked request-per-session estimate and headroom at various daily
visit counts. Two numbers matter more than the raw total:

- **Requests per real page view** — should be small and roughly constant
  (one Worker invocation for the HTML/RSC payload, cache-intercepted static
  assets don't re-invoke the Worker). If this number creeps up across a
  deploy, something is calling the Worker more than once per view.
- **Requests while idle** — should be **zero**. Any nonzero, *sustained*
  idle request rate (not a one-time settle-down burst) is a bug by
  definition, regardless of how small it looks per-tab — it multiplies by
  every open tab, including forgotten background tabs, which is exactly
  what turned a "harmless" 40ms interval into a 20-minute path to 1027.
