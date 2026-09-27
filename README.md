# MonsterScraper

Scrape every Monster Energy can listed on [monsterenergy.com](https://www.monsterenergy.com),
across every country and language the site offers, into clean JSON/CSV. It can also download the
can artwork.

> **Backstory:** I once wanted to build an app for cataloguing Monster Energy drinks, and this
> scraper was supposed to seed its database. Monster wasn't interested in working with me, so the
> app never happened, but the scraper survived. The first version was hacked together in one day
> (October 2023). This is a complete rewrite as a proper, tested Python package.

## What you get

For every can on every locale:

| Field           | Example                                                        |
| --------------- | -------------------------------------------------------------- |
| `id`            | `en-gb/juiced-monster/mango-loco` (unique, stable)             |
| `locale`        | `en-gb`                                                        |
| `category`      | `Juiced Monster` (localised display name)                      |
| `category_slug` | `juiced-monster`                                               |
| `slug`          | `mango-loco`                                                   |
| `name`          | `Juiced Monster Mango Loco`                                    |
| `flavor`        | `Juicy Mango`                                                  |
| `description`   | Marketing copy, in the locale's language                       |
| `callouts`      | `[{"value": "160mg", "label": "Caffeine"}, …]`                 |
| `note`          | `Figures based on 500ml and may vary per region`               |
| `image_url`     | Can artwork (PNG)                                              |
| `logo_url`      | Product logo (PNG)                                             |
| `url`           | Source product page                                            |
| `image_path`    | Local file, relative to the output dir (only with `--images`) |

> Up to 2023 the site also published nutrition tables and ingredient lists. A later redesign
> removed them, so they can no longer be scraped. The callouts (caffeine, sugar or calories,
> depending on the region) are what is left.

## Quickstart

You only need [uv](https://docs.astral.sh/uv/getting-started/installation/). It downloads the
right Python version (pinned in `.python-version`) and every dependency for you.

```bash
git clone https://github.com/FedericoCalabro/MonsterScraper.git
cd MonsterScraper
uv sync
uv run monster-scraper run --images --image-width 200 --csv
```

Results go to `./output`. As of September 2026, a full run finds about **1,000 cans across 61
locales**. The other locales on the site have no drinks catalogue. The site rate-limits
aggressively and the scraper slows itself down to match, so a full run takes about 15 minutes.
To try a single country first:

```bash
uv run monster-scraper run -l en-gb
```

## Usage

```text
uv run monster-scraper [COMMAND] [OPTIONS]
```

| Command   | What it does                                                             | Writes                    |
| --------- | ------------------------------------------------------------------------ | ------------------------- |
| `locales` | Reads the site's country selector                                        | `locales.txt`             |
| `links`   | Visits `/<locale>/energy-drinks/` for each locale                       | `links.txt`               |
| `drinks`  | Scrapes every product page, plus optional images and CSV                 | `drinks.json` (+ extras)  |
| `run`     | Runs all of the above from scratch                                       | everything                |

| Option                | Commands                    | Description                                               |
| --------------------- | --------------------------- | --------------------------------------------------------- |
| `-l, --locale CODE`   | `links`, `drinks`, `run`    | Only scrape this locale (repeatable), e.g. `-l it-it`     |
| `-o, --out DIR`       | all                         | Output directory (default `output`)                       |
| `--images`            | `drinks`, `run`             | Download can images to `<out>/images/…`                   |
| `--image-width N`     | `drinks`, `run`             | Downscale images to `N` px wide (never upscales)          |
| `--csv`               | `drinks`, `run`             | Also write `drinks.csv`                                   |
| `-c, --concurrency N` | all                         | Parallel requests, 1 to 16 (default 4). Please be gentle. |
| `--refresh`           | `links`, `drinks`           | Ignore cached `locales.txt` / `links.txt`                 |
| `-v, --verbose`       | all                         | Debug logging (retries etc.)                              |

`uv run monster-scraper --help` and `uv run monster-scraper <command> --help` show the same
reference. You can also run the package with `uv run python -m monster_scraper`.

### Caching between stages

Each stage saves its result, and later stages reuse it:

- `links` reuses `locales.txt` if it exists.
- `drinks` reuses `links.txt`, filtered by `--locale`. If no cached link matches, it discovers
  links for those locales again.
- `--refresh` makes a command ignore the cache. `run` always starts from scratch.

So after one full run you can re-scrape product pages (for example, to add images) without
crawling the listings again:

```bash
uv run monster-scraper drinks --images --image-width 300
```

### Output layout

```text
output/
├── locales.txt
├── links.txt
├── drinks.json
├── drinks.csv                              # with --csv
└── images/<locale>/<category>/<slug>.png   # with --images
```

<details>
<summary>Sample <code>drinks.json</code> record</summary>

```json
{
  "id": "en-gb/juiced-monster/mango-loco",
  "locale": "en-gb",
  "category": "Juiced Monster",
  "category_slug": "juiced-monster",
  "slug": "mango-loco",
  "name": "Juiced Monster Mango Loco",
  "flavor": "Juicy Mango",
  "description": "Juiced Monster Mango Loco 500ml can - carbonated energy drink with taurine, L-carnitine, inositol and B vitamins. …",
  "note": "Figures based on 500ml and may vary per region",
  "image_url": "https://web-assests.monsterenergy.com/mnst/92c232b6-c27e-487b-b3d6-11eaeb5226e6.png",
  "logo_url": "https://web-assests.monsterenergy.com/mnst/b7c4f349-4cd7-48b5-8cfc-fe113f8882c6.png",
  "url": "https://www.monsterenergy.com/en-gb/energy-drinks/juiced-monster/mango-loco/",
  "callouts": [
    { "value": "160mg", "label": "Caffeine" },
    { "value": "56g", "label": "Sugar" }
  ],
  "image_path": "images/en-gb/juiced-monster/mango-loco.png"
}
```

In the CSV, `callouts` is flattened into one column, e.g. `160mg Caffeine; 56g Sugar`.

</details>

## How it works

1. **Locales.** The home page's country selector links to every `/<xx-yy>/` site.
2. **Links.** Each locale's `/<locale>/energy-drinks/` page lists its products as
   `/<locale>/energy-drinks/<category>/<slug>/`. Locales without a catalogue, or that redirect
   to another locale, are skipped.
3. **Drinks.** Each product page is parsed with [selectolax](https://github.com/rushter/selectolax).
   A few listed pages are empty templates or 404s on the site itself. They are skipped and
   counted in the summary; `-v` lists them. Any other failure is logged as a warning, and the run
   carries on.
4. **Images** (optional). Many locales share the same artwork, so each unique image is
   downloaded once and resized with [Pillow](https://python-pillow.org/). `drinks.json` is
   written before this step starts, so the metadata is kept even if the download is
   interrupted, and written again afterwards with `image_path` filled in.

The site is behind bot protection that blocks ordinary HTTP clients.
[curl_cffi](https://github.com/lexiforest/curl_cffi) makes requests with a real Chrome browser's
TLS fingerprint, so the site serves the normal pages. Requests are limited in number, spaced out,
and retried with exponential backoff. When the site answers `429 Too Many Requests`:

- every worker pauses (honouring `Retry-After` if the site sends one), and
- the delay between requests grows for the rest of the run, so a long crawl settles at a rate
  the site accepts instead of losing pages.

If no drink could be scraped at all (for example, you were blocked), the command exits with
status 1 and leaves the previous `drinks.json` untouched.

## Development

```bash
uv sync                 # installs runtime + dev dependencies into .venv
uv run pytest           # offline test suite (no network needed)
uv run ruff check .     # lint
uv run ruff format .    # format
```

```text
src/monster_scraper/
├── cli.py        # Typer commands, progress bars, stage caching
├── pipeline.py   # async stages: locales → links → drinks → images
├── client.py     # curl_cffi client: concurrency limit, delays, retries
├── parsers.py    # pure HTML → data functions
├── models.py     # Drink / Callout dataclasses
├── images.py     # PNG re-encoding and resizing
└── storage.py    # txt / JSON / CSV writers
tests/
├── fixtures/     # real pages saved from the site (scripts and styles removed)
└── test_*.py
```

The parsers are tested against real HTML saved in `tests/fixtures/`. If the site changes its
markup, save fresh copies of those pages. The failing tests then show which selectors need
updating in `parsers.py`.

## Disclaimer

This is an unofficial, personal project. It is not affiliated with or endorsed by Monster Energy
Company. All product names, images and trademarks belong to their owners. The site's
`robots.txt` currently allows crawling, but please keep concurrency low, respect the site's terms
of use, and don't redistribute the scraped content commercially.
