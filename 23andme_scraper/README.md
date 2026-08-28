# 23andMe Scraper

Interactive Playwright scraper for authenticated 23andMe raw-data pages.

## Install

```bash
uv sync
uv run playwright install chromium
```

## Usage

```bash
uv run 23andme-scraper scrape \
  --start-url "https://you.23andme.com/p/085d7e61a61b313d/tools/data/?chromosome=MT&offset=400" \
  --output-dir output/23andme \
  --state-file state/23andme_auth.json \
  --headed
```

The command opens a real browser window, waits for you to log into 23andMe, then scrapes the raw-data pages and saves:

- `output/23andme/build37.csv`
- `output/23andme/build38.csv`

If `--state-file` already exists, the scraper reuses that Playwright session to avoid logging in again. After you complete a successful login, it saves the updated session back to that file.

## Notes

- The project uses `uv` for dependency management, `click` for the CLI, `loguru` for logging, and `playwright` for browser automation.
- By default the scraper attempts all chromosomes: `1-22`, `X`, `Y`, and `MT`.
- The session file contains login state, so keep it out of git and treat it like a secret.
- If 23andMe changes the table layout, the DOM selectors in `src/twentythreeandme_scraper/scraper.py` are the main place to update.
