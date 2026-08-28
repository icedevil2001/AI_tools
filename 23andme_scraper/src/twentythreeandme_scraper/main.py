from __future__ import annotations

from pathlib import Path

import click
from loguru import logger

from twentythreeandme_scraper.scraper import run_scrape


@click.group()
def cli() -> None:
    """Interactive 23andMe raw-data scraper."""


@cli.command()
@click.option("--start-url", required=True, help="Authenticated 23andMe raw-data page URL.")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("output/23andme"),
    show_default=True,
    help="Directory for build37.csv and build38.csv.",
)
@click.option("--headed/--headless", default=True, show_default=True, help="Show the browser window.")
@click.option(
    "--state-file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("state/23andme_auth.json"),
    show_default=True,
    help="Playwright storage state file used to reuse a logged-in session.",
)
@click.option("--timeout-ms", default=15_000, show_default=True, help="Page wait timeout in milliseconds.")
@click.option("--max-empty-pages", default=2, show_default=True, help="Stop after this many empty pages per chromosome.")
@click.option(
    "--chromosomes",
    default="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,X,Y,MT",
    show_default=True,
    help="Comma-separated chromosome list to scrape.",
)
def scrape(
    start_url: str,
    output_dir: Path,
    headed: bool,
    state_file: Path,
    timeout_ms: int,
    max_empty_pages: int,
    chromosomes: str,
) -> None:
    """Launch a browser, wait for login, and export split CSV files."""

    logger.remove()
    logger.add(lambda message: click.echo(message, nl=False), level="INFO")
    chromosome_list = [value.strip() for value in chromosomes.split(",") if value.strip()]

    build37_path, build38_path = run_scrape(
        start_url=start_url,
        output_dir=output_dir,
        headed=headed,
        state_file=state_file,
        timeout_ms=timeout_ms,
        max_empty_pages=max_empty_pages,
        chromosomes=chromosome_list,
    )

    click.echo(f"Build 37 CSV: {build37_path}")
    click.echo(f"Build 38 CSV: {build38_path}")


if __name__ == "__main__":
    cli()
