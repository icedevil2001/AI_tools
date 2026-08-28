# 23andMe Interactive Scraper Design

## Goal

Build a Python CLI tool that opens a real browser, lets the user log into 23andMe interactively, scrapes raw genetic data rows from the authenticated data pages, and writes separate CSV files for Build 37 and Build 38.

## User Requirements

- Use an interactive browser login flow.
- Use `uv` for project setup and execution.
- Use `click` for the CLI.
- Use `loguru` for logging.
- Export these columns:
  - `Genes`
  - `Marker`
  - `Assembly`
  - `Position`
  - `Variants`
  - `Genotype`
- Split Build 37 and Build 38 into separate output files.

## Recommended Architecture

Create a self-contained `23andme_scraper/` project with:

- `pyproject.toml` managed by `uv`
- `main.py` for the Click CLI entrypoint
- `scraper.py` for Playwright session control and navigation
- `parser.py` for row extraction and normalization helpers
- `models.py` for the row data shape
- `tests/` for unit tests around parsing and build splitting

The browser automation should stay thin. Parsing, normalization, deduplication, and file-splitting should live in pure helper functions so the core logic can be tested without a live login.

## Browser Flow

1. Launch Playwright Chromium in headed mode.
2. Open the 23andMe raw-data page.
3. Pause for manual login and user confirmation.
4. Iterate through data pages or page states until no new rows appear.
5. Extract the six requested columns from each visible row.
6. Deduplicate rows by a stable key such as `marker + assembly + position`.
7. Write `build37.csv` and `build38.csv`.

## Data Handling

The scraper will normalize each row into a single record with these exact output keys:

- `Genes`
- `Marker`
- `Assembly`
- `Position`
- `Variants`
- `Genotype`

Assembly values will be normalized so common variants like `Build 37`, `GRCh37`, `Build 38`, and `GRCh38` can still be routed into the correct output file.

## Error Handling

- Wait for authenticated content before scraping.
- Retry row/table reads when the page is still loading.
- Save progress logs throughout the run.
- Skip malformed rows instead of failing the whole session.
- Write output only from normalized, validated records.

## Testing Strategy

Use unit tests for:

- parsing table rows into normalized records
- assembly normalization
- splitting records into Build 37 and Build 38 collections
- CSV header ordering

Live browser scraping will remain a manual verification step because it depends on the user account and interactive login.

## CLI Shape

The CLI should be simple and explicit:

```bash
uv run python main.py scrape \
  --start-url "https://you.23andme.com/p/085d7e61a61b313d/tools/data/?chromosome=MT&offset=400" \
  --output-dir output/23andme \
  --headed
```

The command will open the browser, wait for login, scrape records, and save:

- `output/23andme/build37.csv`
- `output/23andme/build38.csv`

## Constraints and Assumptions

- The tool depends on the user completing login manually in the browser.
- The exact DOM may vary, so selectors should prefer text/semantic anchors over brittle class names where possible.
- If 23andMe changes the page structure substantially, only the thin scraper layer should need adjustment.
