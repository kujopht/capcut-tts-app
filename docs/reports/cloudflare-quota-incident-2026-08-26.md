# Cloudflare Workers free-tier quota exhaustion — 2026-08-26

## What happened

`fanfic.world` went fully down (Cloudflare Error 1027, "the owner has
reached their plan limits") during this session. Root cause: a Next.js
16 client-router bug (or an interaction between it and OpenNext's
Cloudflare cache-interception layer — never fully isolated, out of our
control to patch) meant every `<Link>` element near/in the browser
viewport re-issued its RSC segment-prefetch request roughly every 40ms,
**forever**, for as long as a tab stayed open — regardless of whether
the previous identical request had already succeeded with
`x-nextjs-stale-time: 300`. Measured on a real deployed Worker
(`wrangler dev` against the actual OpenNext build, which reproduces
this — plain `next start` never does): **~3,000–3,500 requests per 30
seconds of idle, from a single browser tab**, on `/` alone.

At that rate a single open tab exhausts the Workers Free plan's
100,000-requests/day ceiling in well under 20 minutes. Combined with
this session's own repeated live measurement passes earlier in the
night, the quota was fully consumed and the whole zone returned 1027
until Cloudflare's daily reset (00:00 UTC).

## The fix

Next.js's `<Link prefetch={false}>` prop fully disables both the
viewport-triggered (`IntersectionObserver`) and hover-triggered
prefetch paths at the React-component level, before any observer is
even attached — confirmed by reading the actual shipped Next.js 16.3.0
client source (`next/dist/client/components/links.js`), not just the
docs. Applied to every `<Link>` across the whole `web/src` tree whose
destination is a small, already-prerendered static page — the
navigation header, the homepage's hero/portal cards, and every
CTA/breadcrumb/footer link pointing at `/`, `/fanfic`, `/animation`,
`/community`, `/library`, `/write`, `/login`, `/studio`,
`/image-studio`, `/leaderboard`, `/account`, `/notifications`,
`/creator/apply`. Genuinely dynamic per-item routes (chapters, novels,
animation episodes/watch, posts, user profiles) were deliberately left
untouched — confirmed separately that those already prefetch exactly
once, correctly, with no storm.

Shipped across three PRs as the true scope became clear through
successive local measurement (each round found the storm had
*relocated* to a still-unpatched `<Link>`, not disappeared) — see
`web/tests/static-link-prefetch.test.mjs` for the standing regression
test that scans the whole tree for this pattern going forward:

- PR #63 — header nav links
- PR #64 — homepage's own hero/portal/CTA links
- PR #65 — the remaining gaps the first two sweeps' regex missed: bare
  `href="/"`, query-string-suffixed hrefs (`?next=...`), and ternary
  hrefs (`href={profile ? "/write" : "/login"}`) — found by rebuilding
  the actual Worker locally and measuring again, not by inspection.

Final verified result (same local Worker build, same 6 pages, 30s AND
2-minute idle): **zero** RSC prefetch requests. The only network
activity observed was a bounded, one-time initial data/asset load in
the first second of each page visit.

## Monitoring, so this doesn't silently recur

### Right now, zero setup: the dashboard

Cloudflare Dashboard → **Workers & Pages** → `fanfic-web` → **Metrics**
tab shows requests, errors, CPU time, and sub-requests over 24h/7d/30d
windows, already available on the Free plan with no configuration.
This is the fastest way to eyeball "is something spiking" — check it
after any frontend deploy for the first hour or so.

### Automatable: the GraphQL Analytics API

Cloudflare's Analytics API (`https://api.cloudflare.com/client/v4/graphql`)
exposes a Workers invocation dataset queryable with a plain API token —
**no Workers Paid plan required**, this is a reporting/control-plane
call, separate from the Worker's own request quota. The OAuth token
`wrangler` currently uses for deploys (`workers:write` scope only) does
**not** include analytics read access, so a small dedicated token is
needed:

1. Cloudflare dashboard → **My Profile** → **API Tokens** → **Create
   Token** → **Custom token**.
2. Permissions: **Account** → **Account Analytics** → **Read**. Scope
   it to the one account (`Kujopht@gmail.com's Account`,
   `a0084ee7d0f170b2b13bd0ebd5edbd76`). No zone/DNS/other permissions
   needed — keep this token narrowly scoped.
3. Save the token somewhere the monitoring script can read it (e.g. an
   environment variable on the existing GCE VM, which is already
   running and paid for — no new infrastructure needed).

Example query (adjust the dataset name if Cloudflare has renamed it —
verify once against the dashboard's own GraphQL explorer before relying
on it):

```graphql
query WorkerRequests($accountTag: String!, $since: Time!, $until: Time!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersInvocationsAdaptive(
        limit: 1000
        filter: { datetime_geq: $since, datetime_leq: $until, scriptName: "fanfic-web" }
      ) {
        sum { requests errors }
        dimensions { datetimeHour }
      }
    }
  }
}
```

A lightweight script (Python, `httpx` — already a project dependency)
run on a schedule (cron on the GCE VM, or a scheduled GitHub Actions
workflow — both free) can poll this hourly, sum the day's running
total, and alert (write to a log the operator checks, or push to
whatever notification channel is already in use — Slack/email/etc.)
when a threshold is crossed. Not implemented in this pass — this
report documents the exact path so it can be added in ~30 minutes of
follow-up work once someone wants it, without re-investigating from
scratch.

### Thresholds

The user's own framework (normal / warning / critical) is right, but
putting real numbers on "normal" requires actual post-fix traffic data,
which doesn't exist yet — this incident happened *because* of runaway
traffic, so nothing measured during it reflects real usage. Rather than
invent a number, here's the reasoning to apply once a few days of clean
data exist:

- **Normal**: whatever the actual daily total settles to post-fix.
  With the storm eliminated, a legitimate page view now costs ~1-2
  cheap Worker invocations (cache-intercepted, not the expensive
  5.2MB-bundle path). For a private, non-commercial, 13-novel MVP,
  expect this to land in the low hundreds to low thousands per day,
  not tens of thousands — but confirm against real numbers rather than
  trusting that estimate.
- **Warning**: a meaningful jump over that established baseline —
  e.g., 3-5× a rolling 7-day average, which would catch a new runaway
  loop (a different bug, a bad crawler, a bot) long before it becomes
  an outage.
- **Critical**: a trajectory that would exhaust 100k/day if it
  continued at the current hourly rate — i.e., extrapolate the last
  1-2 hours' rate forward to end-of-day and alert if that projection
  crosses the ceiling, rather than waiting for the raw daily counter
  to actually hit it.

## What this incident does *not* mean

The architecture itself is not the problem, and no migration is being
proposed. `wrangler.jsonc` already documents (predating this incident)
that an earlier session evaluated skipping the Worker entirely for
navigation by serving prerendered HTML straight from static assets —
and found the static-file router matches by path only, ignoring the
RSC/prefetch headers, so every client-side navigation would receive
full HTML where it expected an RSC payload, forcing full-page reloads
that unmount `AudioEngineProvider` and break audio playback persisting
across route changes. That trade was correctly rejected then, and nothing
in this incident changes that conclusion — the request-per-navigation
cost is real but small (confirmed cache-intercepted, cheap) and was
never the actual problem; the *unbounded, repeating* prefetch storm
was, and that's now fixed at the source.
