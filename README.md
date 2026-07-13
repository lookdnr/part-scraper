# part-scraper

Tracks GPU and DDR5 RAM prices at UK retailers and pushes a phone
notification (via [ntfy.sh](https://ntfy.sh)) when a price is genuinely good
*relative to its own recent history* — not just below a fixed number.

Currently tracked sites: **Scan**, **Novatech**, **AWD-IT**. All three were
verified live: their robots.txt permits product pages for generic crawlers,
they serve full HTML to a plain, honestly-identified HTTP client, and they
embed the price as schema.org microdata. Overclockers, CCL, Box, Currys,
Ebuyer and idealo were tested and rejected — see
[docs/architecture.md](docs/architecture.md).

## Setup

1. Push this repo to GitHub (private is fine).
2. Install the **ntfy** app on your phone ([Android/iOS](https://ntfy.sh)),
   and subscribe to a topic with an unguessable name, e.g.
   `luke-parts-x7k2m9qp4w`. The topic name is the only auth — anyone who
   knows it can post to it, so treat it like a password.
3. In the repo: Settings → Secrets and variables → Actions → new secret
   `NTFY_TOPIC` with that topic name.
4. That's it. The workflow in `.github/workflows/track.yml` runs twice a day,
   appends prices to `data/history/`, commits them back, and notifies on
   deals. Trigger it once manually (Actions tab → *Track prices* → Run
   workflow) to check the plumbing.

Local run:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py --dry-run -v     # fetch + evaluate, write/send nothing
.venv/bin/python run.py                  # real run (writes history; notifies if NTFY_TOPIC set)
```

## How deal detection works (and why)

Raw observations are stored per **listing** (one shop's page for one SKU).
Deals are evaluated per **product** on its *best-price series*: for each day,
the minimum in-stock price across all that product's listings. This matters —
a "drop" at one shop that merely matches what another shop already charged is
not a deal.

Out-of-stock listings are recorded but excluded from all statistics. A price
you can't click "buy" on is not a price (Scan in particular leaves a
99999.99 placeholder on unbuyable products, which would poison any average).

Two signals, evaluated once ≥ 14 days of history exist, over a 30-day
window (all tunable in `config/products.yaml`):

1. **New rolling low** — today's best price beats the previous 30-day
   minimum by ≥ 2%. This is the core "cheapest it's been in a month" signal;
   the 2% floor stops £1 jitter from paging you.
2. **Sharp drop vs trailing median** — today's best price is ≥ 10% below
   the 30-day *median*. This catches a real discount even when the price
   was briefly lower at some point in the window (where signal 1 stays
   silent). Median rather than mean because a single day of spiked or
   mis-parsed pricing shouldn't drag the baseline.

**Bootstrapping.** There is no free, reliable price-history API for UK PC
retail to backfill from (idealo/PriceSpy block scraping; CamelCamelCamel is
Amazon-only), so the first two weeks are inherently data-poor. Between 7 and
14 days of history a cruder rule applies: alert only if today beats
*everything seen so far* by ≥ 5%. Under 7 days: record silently. You lose at
most a week of alerts, and you never get alerts based on statistics too thin
to mean anything.

**Cooldown.** After alerting on a product it stays quiet for 3 days unless
the price falls a further 3% below the alerted price — otherwise a stable
sale price would notify you every run.

## Adding a tracked product

Add a block to `config/products.yaml`:

```yaml
  - id: my-new-product            # unique slug; becomes history filenames
    name: Human-readable name     # used in notifications
    listings:
      - site: scan                # parser key: scan | novatech | awdit
        url: https://www.scan.co.uk/products/...
      - site: novatech
        url: https://www.novatech.co.uk/products/...
```

Then verify it parses before trusting it:

```bash
.venv/bin/python run.py --dry-run -v --product my-new-product
```

Prefer the *same SKU* across shops within one product, so the best-price
series compares like with like. Different SKUs of the same chip (e.g. two
different 5070 Ti models) should be separate products.

## Adding a site

1. Check `https://site/robots.txt` allows product pages for `User-agent: *`,
   and that `curl -A "part-price-tracker/0.1 (...)" <product-url>` returns
   real HTML with the price in it (look for `itemprop="price"` or JSON-LD).
   If you get a 403/Cloudflare page, the site is off-limits to this design —
   don't work around it.
2. Create `pricetracker/parsers/<site>.py` with a `@register("<site>")`
   function returning a `ParseResult`. If the site uses schema.org microdata,
   `microdata.extract_offer()` probably does the whole job.
3. Import it in `pricetracker/parsers/__init__.py`.

## Debugging a parser that stopped finding a price

Symptoms: `FAILED ParserError: ...` in the run log, or the "Tracker broken"
notification (sent automatically after 5 consecutive failed runs for a
listing).

1. Reproduce locally: `.venv/bin/python run.py --dry-run -v --product <id>`.
2. Fetch the page the way the tracker does and inspect it:
   ```bash
   curl -s -A "part-price-tracker/0.1 (personal price tracker)" <url> -o /tmp/page.html
   grep -o 'itemprop="price"[^>]*' /tmp/page.html
   ```
   - **HTTP 404 / redirect to category page** → the product was delisted;
     replace or remove the listing in the config.
   - **HTTP 403 or a Cloudflare/captcha page** → the site started blocking
     plain clients; the listing can't be tracked this way anymore.
   - **200 but no `itemprop="price"`** → the site changed its markup. Look
     for the price in JSON-LD (`application/ld+json`), OpenGraph
     (`product:price:amount`) or the visible HTML, and update the site
     parser in `pricetracker/parsers/`.
3. A wrong-but-plausible price (e.g. a related product's) would be worse
   than a failure — if you change a parser, check its output against the
   price shown in a browser before trusting it.

Note: failure counters live in `data/state.json`; history CSVs in
`data/history/` are append-only and safe to inspect or plot.

## Politeness guarantees

All requests go through `pricetracker/fetch.py`, which enforces: an honest
identifying user-agent (with contact address), robots.txt checked per host
per run, ≥ 6 s between requests to the same host, ≥ 2 s globally, and no
retries hammering. The schedule is twice daily; with the default config
that's ~5 requests per site per day.
