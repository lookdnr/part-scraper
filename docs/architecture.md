# Architecture and trade-offs

## What runs where

```
GitHub Actions (cron, 2×/day)
  └─ run.py
       ├─ config/products.yaml      what to track, thresholds
       ├─ pricetracker/fetch.py     polite HTTP (UA, robots, rate limit)
       ├─ pricetracker/parsers/     per-site HTML → (price, in_stock)
       ├─ pricetracker/history.py   CSV per listing + state.json, in git
       ├─ pricetracker/deals.py     is today's best price a deal?
       └─ pricetracker/notify.py    ntfy.sh push
  └─ git commit data/ && push       ← persistence between runs
```

## Site selection — what was actually tested (2026-07)

Every candidate was probed live with an honest user-agent before writing any
parser:

| Site | robots.txt | Plain HTTP fetch | Verdict |
|---|---|---|---|
| Scan.co.uk | allows product pages | 200, full HTML, microdata price | ✅ tracked |
| Novatech | allows product pages | 200, microdata price | ✅ tracked |
| AWD-IT | allows product pages | 200, microdata + OpenGraph price | ✅ tracked |
| Overclockers | allows | **403 Cloudflare** | ❌ blocks non-browser clients |
| CCL | allows | **403 Cloudflare captcha** | ❌ same |
| Box.co.uk | — | **403 Cloudflare** | ❌ same |
| Currys | **403 even on robots.txt** (Akamai) | — | ❌ |
| Ebuyer | unreachable (timeout) | — | ❌ |
| idealo.co.uk | 503 | — | ❌ aggregator, anti-bot |
| PCPartPicker | robots allows, but Cloudflare-fronted; content-signals restrict reuse | — | ❌ |

Three direct retailers over an aggregator: aggregators would give more
coverage from one parser, but every UK aggregator tested actively blocks
non-browser clients, and scraping through that contradicts the
be-a-decent-citizen constraint. Three independent retailers with overlapping
SKUs still give cross-shop best-price comparison for the products that matter.

**On the blocked sites**: they could be scraped with Playwright plus
browser-fingerprint spoofing. That was deliberately not done. It's slower,
flakier in CI, an arms race you lose eventually, and — since the blocking is
explicit — impolite. Cloudflare also blocks datacenter IPs like GitHub
runners regardless of browser tricks. If Overclockers coverage ever matters
enough, the honest route is their public price feeds/newsletter, not evasion.

All three chosen sites expose the price as schema.org microdata
(`itemprop="price"`). That's the least fragile thing on a retail page: it
feeds Google Shopping, so retailers keep it working through redesigns, and it
gives machine-readable stock state (`InStock` / `PreOrder`) — which caught a
real quirk: Scan publishes a 99999.99 placeholder price on unbuyable
products. Parsing the visible price text would have ingested that.

## Scheduling: GitHub Actions cron

- **Free** for public and (within minutes quota) private repos; a run takes
  ~3 min including polite delays.
- **No server.** The alternative "no server" options are worse fits: a
  Raspberry Pi is a server you maintain; Cloudflare Workers' free tier can't
  easily persist growing history or run >CPU-limited scrapes.
- Known wart: GitHub may delay or occasionally skip scheduled runs, and
  disables cron on repos with 60 days of no activity — but the history
  commits themselves count as activity while the tracker works. Odd-minute
  cron times (`17 9`, `43 17`) reduce delay from the top-of-hour thundering
  herd.

## Persistence: CSVs committed back to the repo

Git-as-database. For this write pattern (append ~12 rows twice a day, single
writer thanks to the workflow `concurrency` group) it is genuinely the right
tool: free, versioned, diffable, survives runner recycling, and trivially
plottable later. One CSV per listing keeps commits conflict-free and lets you
delete one product's history without touching the rest. The repo grows by a
few KB/day — irrelevant for years.

`data/state.json` holds the small mutable state (per-product alert cooldowns,
per-listing consecutive-failure counters) separately from the append-only
history.

## Deal logic placement

Deal detection is a pure function over (today's best price, daily series,
thresholds) with no I/O — see `tests/test_deals.py`. The full rationale for
the two-signal design (rolling low + median drop), bootstrap, and cooldown is
in the README, since it's part of operating the tool.

## Notifications: ntfy.sh

- **ntfy.sh (chosen)**: free, no account, no API key; POST to a topic, phone
  app subscribes. Failure mode is graceful (alerts also appear in the run
  log). Weakness: a topic name is the only auth, so it must be unguessable
  and kept in a GitHub secret.
- Pushover: nicer auth model but a paid app (one-off) — excluded by the
  no-paid-services rule.
- Telegram bot: free and robust but needs a bot token, chat-id discovery,
  and more moving parts for the same outcome.
- Email: free but not push, and deal alerts are time-sensitive.

## Failure containment

- Each listing is fetched/parsed inside its own try/except; a dead site or
  changed markup marks that listing FAILED and the run continues.
- Parse failures write **nothing** to history (no zeros, no placeholders) —
  a broken parser can't corrupt the statistics it will be judged against
  after it's fixed.
- After 5 consecutive failures for a listing you get a "Tracker broken"
  push, so silent rot is bounded at ~2.5 days.
- The run exits non-zero only if *every* listing failed (network-level
  problem), which shows up as a red run in the Actions tab.

## Honest limitations

- **Two samples/day misses flash sales** shorter than ~12 h. Raising the
  cron frequency is one line, but 2×/day was chosen as the polite default;
  the deal signals work on daily granularity anyway.
- **Cold start:** full signal quality arrives after 14 days of history; the
  bootstrap rule covers days 7–14. Nothing to backfill from — no free UK
  price-history API exists.
- **Fixed SKU set:** it tracks the configured pages, so it won't spot a
  different 5070 model being cheap. Adding SKUs is config-only; auto-
  discovering them from category pages would be the next feature, at the
  cost of heavier, less polite crawling.
- **Retailer set is the fragile part.** Any of the three could adopt
  Cloudflare tomorrow; the failure-alert path is designed around exactly
  that, and the response is replacing the site, not evading the block.
