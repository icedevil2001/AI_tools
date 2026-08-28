# 23andMe Scraper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a uv-managed Python CLI that opens a headed Playwright browser for interactive 23andMe login, scrapes raw data rows, and writes separate Build 37 and Build 38 CSV files.

**Architecture:** The project will isolate browser automation from parsing and output logic. Playwright handles navigation and authenticated page access, while pure helpers normalize rows, deduplicate records, split assemblies, and write CSV files.

**Tech Stack:** Python 3.11+, uv, click, loguru, playwright, pytest

---

### Task 1: Scaffold the package

**Files:**
- Create: `23andme_scraper/pyproject.toml`
- Create: `23andme_scraper/README.md`
- Create: `23andme_scraper/__init__.py`

**Step 1: Create the project metadata**

Add a `pyproject.toml` with dependencies for `click`, `loguru`, and `playwright`, plus a test dependency on `pytest`.

**Step 2: Add a short README**

Document the purpose, install command, and basic usage with `uv run`.

**Step 3: Verify the scaffold exists**

Run: `rg --files 23andme_scraper`
Expected: package files are present

### Task 2: Write failing parser tests

**Files:**
- Create: `23andme_scraper/tests/test_parser.py`
- Create: `23andme_scraper/parser.py`
- Create: `23andme_scraper/models.py`

**Step 1: Write the failing tests**

Add tests for:

- normalizing a raw row into the six output columns
- mapping assembly labels to build buckets
- splitting mixed rows into Build 37 and Build 38 collections

**Step 2: Run tests to verify they fail**

Run: `uv run pytest 23andme_scraper/tests/test_parser.py -v`
Expected: FAIL because parser/model code does not exist yet

**Step 3: Write the minimal implementation**

Add a row model plus parser helpers for normalization and build splitting.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest 23andme_scraper/tests/test_parser.py -v`
Expected: PASS

### Task 3: Write failing CSV output tests

**Files:**
- Create: `23andme_scraper/tests/test_output.py`
- Create: `23andme_scraper/output.py`

**Step 1: Write the failing tests**

Add tests for:

- CSV headers being written in the requested order
- build37/build38 files receiving the correct rows

**Step 2: Run tests to verify they fail**

Run: `uv run pytest 23andme_scraper/tests/test_output.py -v`
Expected: FAIL because output helpers do not exist yet

**Step 3: Write the minimal implementation**

Add CSV writing helpers using the normalized row model.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest 23andme_scraper/tests/test_output.py -v`
Expected: PASS

### Task 4: Write failing CLI tests

**Files:**
- Create: `23andme_scraper/tests/test_cli.py`
- Create: `23andme_scraper/main.py`

**Step 1: Write the failing tests**

Add tests for:

- the `scrape` command existing
- the default output directory
- the CLI passing user options into the scrape runner

**Step 2: Run tests to verify they fail**

Run: `uv run pytest 23andme_scraper/tests/test_cli.py -v`
Expected: FAIL because the CLI entrypoint does not exist yet

**Step 3: Write the minimal implementation**

Add a Click CLI with a `scrape` command and the key options.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest 23andme_scraper/tests/test_cli.py -v`
Expected: PASS

### Task 5: Write failing scraper tests

**Files:**
- Create: `23andme_scraper/tests/test_scraper.py`
- Create: `23andme_scraper/scraper.py`

**Step 1: Write the failing tests**

Add focused tests around:

- deduplicating normalized records
- deciding when pagination should stop
- extracting row dictionaries from a page fragment helper

**Step 2: Run tests to verify they fail**

Run: `uv run pytest 23andme_scraper/tests/test_scraper.py -v`
Expected: FAIL because scraper helpers do not exist yet

**Step 3: Write the minimal implementation**

Add the non-browser helper logic first, then the Playwright-backed scraper runner.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest 23andme_scraper/tests/test_scraper.py -v`
Expected: PASS

### Task 6: Implement the interactive Playwright flow

**Files:**
- Modify: `23andme_scraper/scraper.py`
- Modify: `23andme_scraper/main.py`

**Step 1: Add headed browser launch**

Launch Chromium in headed mode by default and open the user-provided start URL.

**Step 2: Add interactive login pause**

Prompt the user in the terminal to finish login, then continue when they confirm.

**Step 3: Add scraping loop**

Read the current raw-data table, normalize rows, attempt to navigate or advance, and stop once no new records appear.

**Step 4: Add logging**

Use `loguru` for session start, page progress, row counts, retries, and output paths.

**Step 5: Verify tests still pass**

Run: `uv run pytest 23andme_scraper/tests -v`
Expected: PASS

### Task 7: Document usage

**Files:**
- Modify: `23andme_scraper/README.md`

**Step 1: Document install and browser setup**

Include:

- `uv sync`
- `uv run playwright install chromium`
- the scrape command example

**Step 2: Document the manual-login flow**

Explain that the script pauses for authenticated access and then saves `build37.csv` and `build38.csv`.

**Step 3: Verify docs references**

Run: `sed -n '1,220p' 23andme_scraper/README.md`
Expected: usage instructions are present and accurate

### Task 8: Final verification

**Files:**
- Verify: `23andme_scraper/`

**Step 1: Run the full test suite**

Run: `uv run pytest 23andme_scraper/tests -v`
Expected: PASS

**Step 2: Smoke-check the CLI help**

Run: `uv run python 23andme_scraper/main.py --help`
Expected: command help renders successfully

**Step 3: Manual runtime check**

Run: `uv run python 23andme_scraper/main.py scrape --help`
Expected: scrape options render successfully
