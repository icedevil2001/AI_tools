from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import click
from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from twentythreeandme_scraper.models import CSV_COLUMNS, RawDataRow
from twentythreeandme_scraper.output import write_split_csvs
from twentythreeandme_scraper.parser import normalize_row


DEFAULT_CHROMOSOMES = [str(index) for index in range(1, 23)] + ["X", "Y", "MT"]
SCRAPE_SCHEME = "https"
SCRAPE_HOST = "you.23andme.com"
SCRAPE_PATH = "/tools/data/"
TABLE_SELECTOR = "#marker-table"
VISIBLE_TABLE_SELECTOR = "#marker-table:not(.hide)"
BODY_ROW_SELECTOR = "#marker-table tbody tr:not(.js-visual-header)"
LOAD_MORE_BUTTON_SELECTOR = "#marker-table .load-more-button"
LOADING_SPINNER_SELECTOR = "#marker-table .js-loading"



def dedupe_rows(rows: list[RawDataRow]) -> list[RawDataRow]:
    unique_rows: list[RawDataRow] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for row in rows:
        if row.dedupe_key in seen_keys:
            continue
        seen_keys.add(row.dedupe_key)
        unique_rows.append(row)

    return unique_rows


def should_stop_scraping(new_rows_count: int, consecutive_empty_pages: int, max_empty_pages: int) -> bool:
    return new_rows_count == 0 and consecutive_empty_pages >= max_empty_pages


def run_scrape(
    *,
    start_url: str,
    output_dir: Path,
    headed: bool,
    state_file: Path,
    timeout_ms: int,
    max_empty_pages: int,
    chromosomes: list[str] | None = None,
) -> tuple[Path, Path]:
    all_rows: list[RawDataRow] = []
    seen_keys: set[tuple[str, str, str]] = set()
    chromosomes_to_scrape = chromosomes or DEFAULT_CHROMOSOMES

    logger.info("Launching browser for interactive 23andMe scraping")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(storage_state=str(state_file) if state_file.exists() else None)
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        logger.info("Opening start URL: {}", start_url)
        page.goto(start_url, wait_until="domcontentloaded")
        if state_file.exists():
            logger.info("Loaded saved browser session from {}", state_file)
        else:
            logger.info("No saved session found at {}; manual login required", state_file)

        click.confirm(
            "Finish logging into 23andMe in the opened browser, then confirm to start scraping",
            default=True,
            abort=True,
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(state_file))
        logger.info("Saved browser session to {}", state_file)

        for chromosome in chromosomes_to_scrape:
            chromosome_rows = scrape_chromosome(
                page=page,
                start_url=start_url,
                chromosome=chromosome,
                timeout_ms=timeout_ms,
                max_empty_pages=max_empty_pages,
            )
            for row in chromosome_rows:
                if row.dedupe_key in seen_keys:
                    continue
                seen_keys.add(row.dedupe_key)
                all_rows.append(row)

        browser.close()

    deduped_rows = dedupe_rows(all_rows)
    build37_path, build38_path = write_split_csvs(deduped_rows, output_dir)
    logger.info("Wrote {} total unique rows", len(deduped_rows))
    logger.info("Build 37 CSV: {}", build37_path)
    logger.info("Build 38 CSV: {}", build38_path)
    return build37_path, build38_path


def scrape_chromosome(
    *,
    page: Page,
    start_url: str,
    chromosome: str,
    timeout_ms: int,
    max_empty_pages: int,
) -> list[RawDataRow]:
    rows: list[RawDataRow] = []
    consecutive_empty_pages = 0

    logger.info("Scraping chromosome {}", chromosome)

    url = build_data_url(start_url=start_url, chromosome=chromosome, offset=0)
    page.goto(url, wait_until="domcontentloaded")
    wait_for_data_table(page, timeout_ms=timeout_ms)

    while True:
        page_rows = dedupe_rows(extract_rows_from_page(page))
        new_rows = [row for row in page_rows if row.dedupe_key not in {existing.dedupe_key for existing in rows}]
        logger.info("Chromosome {} currently shows {} row(s), {} new", chromosome, len(page_rows), len(new_rows))

        if new_rows:
            rows.extend(new_rows)
            consecutive_empty_pages = 0
        else:
            consecutive_empty_pages += 1

        if not click_load_more(page, timeout_ms=timeout_ms):
            logger.info("No more load-more button for chromosome {}", chromosome)
            break

        if should_stop_scraping(
            new_rows_count=len(new_rows),
            consecutive_empty_pages=consecutive_empty_pages,
            max_empty_pages=max_empty_pages,
        ):
            logger.info("Stopping chromosome {} after {} stale load(s)", chromosome, consecutive_empty_pages)
            break

    return dedupe_rows(rows)


def build_data_url(*, start_url: str, chromosome: str, offset: int) -> str:
    parsed = urlparse(start_url)
    query = {
        "chromosome": [chromosome],
        "offset": [str(offset)],
    }
    encoded_query = urlencode(query, doseq=True)
    return urlunparse(
        parsed._replace(
            scheme=SCRAPE_SCHEME,
            netloc=SCRAPE_HOST,
            path=SCRAPE_PATH,
            query=encoded_query,
            params="",
            fragment="",
        )
    )


def wait_for_data_table(page: Page, timeout_ms: int) -> None:
    selectors = [
        VISIBLE_TABLE_SELECTOR,
        TABLE_SELECTOR,
        BODY_ROW_SELECTOR,
    ]
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=timeout_ms)
            return
        except PlaywrightTimeoutError:
            continue
    logger.warning("No table selector matched before timeout; attempting best-effort extraction")


def extract_rows_from_page(page: Page) -> list[RawDataRow]:
    headers = [header.strip() for header in page.locator(f"{TABLE_SELECTOR} thead th").all_inner_texts()]
    body_rows = page.locator(BODY_ROW_SELECTOR)
    rows: list[RawDataRow] = []

    for index in range(body_rows.count()):
        cells = [cell.strip() for cell in body_rows.nth(index).locator("td").all_inner_texts()]
        if not cells:
            continue
        raw_row = map_cells_to_columns(headers, cells)
        if raw_row is None:
            continue
        rows.append(normalize_row(raw_row))

    return rows


def click_load_more(page: Page, timeout_ms: int) -> bool:
    button = page.locator(LOAD_MORE_BUTTON_SELECTOR)
    if button.count() == 0 or not button.first.is_visible():
        return False

    before_count = page.locator(BODY_ROW_SELECTOR).count()
    button.first.click()

    try:
        page.wait_for_function(
            """([selector, beforeCount]) => {
                const rows = document.querySelectorAll(selector);
                return rows.length > beforeCount;
            }""",
            arg=[BODY_ROW_SELECTOR, before_count],
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        spinner = page.locator(LOADING_SPINNER_SELECTOR)
        if spinner.count() and spinner.first.is_visible():
            try:
                spinner.first.wait_for(state="hidden", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                return False
        else:
            return False

    return True


def map_cells_to_columns(headers: list[str], cells: list[str]) -> dict[str, str] | None:
    if headers and len(headers) >= len(CSV_COLUMNS):
        header_map = dict(zip(headers, cells))
        if all(column in header_map for column in CSV_COLUMNS):
            return {column: header_map[column] for column in CSV_COLUMNS}

    if len(cells) >= len(CSV_COLUMNS):
        return dict(zip(CSV_COLUMNS, cells[: len(CSV_COLUMNS)]))

    return None
