from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from loguru import logger

from codex_usage_collector.collector import run_collection
from codex_usage_collector.config import load_config
from codex_usage_collector.credits import load_credit_mapping
from codex_usage_collector.logger import configure_logging
from codex_usage_collector.pricing import load_model_pricing
from codex_usage_collector.reporting import UsageReport, build_usage_report
from codex_usage_collector.storage import load_existing


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], show_default=True)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"]),
)
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """Collect and aggregate Codex session usage data."""
    configure_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level


@cli.command()
@click.option(
    "--config",
    "config_path",
    default=Path("config.yaml"),
    show_default=True,
    type=click.Path(path_type=Path, dir_okay=False),
)
def collect(config_path: Path) -> None:
    """Collect usage data using a YAML config file."""
    try:
        config = load_config(config_path)
        result, before_count, after_count = run_collection(config)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    for host_stat in result.host_stats:
        logger.info(
            "Host {}: files={}, records={}, parse_failures={}, read_failures={}",
            host_stat.hostname,
            host_stat.files_seen,
            host_stat.records_added,
            host_stat.parse_failures,
            host_stat.read_failures,
        )

    click.echo(
        "Saved "
        f"{after_count} total records "
        f"({after_count - before_count} new, {len(result.records)} parsed this run)"
    )


@cli.command()
@click.option(
    "--config",
    "config_path",
    default=Path("config.yaml"),
    show_default=True,
    type=click.Path(path_type=Path, dir_okay=False),
)
@click.option(
    "--days",
    default=None,
    type=click.IntRange(min=1),
    help="Limit the report to the last N days. Omit to report all collected history.",
)
@click.option(
    "--interval",
    default="daily",
    show_default=True,
    type=click.Choice(["daily", "weekly", "monthly", "session"]),
)
@click.option(
    "--show",
    "show_mode",
    default="all",
    show_default=True,
    type=click.Choice(["all", "tokens", "credits", "price"]),
)
@click.option("--by-host", is_flag=True, help="Show one row per period and host.")
@click.option("--host", "host_filter", help="Filter the report to one host.")
@click.option("--json", "json_output", is_flag=True, help="Output the report as JSON.")
@click.option("--color/--no-color", "color_output", default=False, help="Colorize table output.")
def report(
    config_path: Path,
    days: int | None,
    interval: str,
    show_mode: str,
    by_host: bool,
    host_filter: str | None,
    json_output: bool,
    color_output: bool,
) -> None:
    """Print aggregated usage for the last N days."""
    try:
        config = load_config(config_path)
        credit_rates = load_credit_mapping(config.credit_mapping.path)
        model_pricing = load_model_pricing(config.model_cost.url)
        usage_report = build_usage_report(
            load_existing(config.storage.path),
            days=days,
            interval=interval,
            credit_rates=credit_rates,
            model_pricing=model_pricing,
            weekly_credit_limit=config.credit_limit.weekly_limit,
            credit_week_ends_on=config.credit_limit.end_of_week,
            credit_reset_time=config.credit_limit.reset_time,
            credit_roll_over=config.credit_limit.roll_over,
            by_host=by_host,
            host_filter=host_filter,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(json.dumps(usage_report.to_dict(), indent=2))
        return

    if not usage_report.rows:
        click.echo(f"No usage records found for {_report_window(days)} at {config.storage.path}.")
        return

    click.echo(
        f"Usage summary for {_report_window(days)} ({interval}) from {config.storage.path}:"
    )
    click.echo(
        _format_report_table(
            usage_report, show_mode=show_mode, by_host=by_host, color_output=color_output
        )
    )


def _format_report_table(
    report: UsageReport, *, show_mode: str, by_host: bool, color_output: bool = False
) -> str:
    rows: list[dict[str, Any]] = []
    for row in report.rows:
        rows.append(_format_report_row(row, show_mode=show_mode, by_host=by_host))

    rows.append(_format_total_row(report, show_mode=show_mode, by_host=by_host, color_output=color_output))

    return _records_to_table(rows, color_output=color_output)


def _format_report_row(row: dict[str, Any], *, show_mode: str, by_host: bool) -> dict[str, Any]:
    formatted: dict[str, Any] = {
        "Period": row["period_start"],
        "Host": row["host"] if by_host else f'{row["hosts"]} host(s)',
        "Sessions": row["sessions"],
        "Models": ", ".join(row["models"]),
    }
    if show_mode in {"all", "tokens"}:
        formatted.update(
            {
                "Input": _format_int(row["non_cached_input_tokens"]),
                "Cached Input": _format_int(row["cached_input_tokens"]),
                "Output": _format_int(row["output_tokens"]),
                "Reasoning": _format_int(row["reasoning_output_tokens"]),
                "Total Tokens": _format_int(row["total_tokens"]),
            }
        )
    if show_mode in {"all", "credits"}:
        formatted["Credits"] = f'{row["credits"]:.2f}'
        formatted["Credit Remaining"] = _row_credit_remaining(row)
    if show_mode in {"all", "price"}:
        formatted["Cost USD"] = f'${row["cost_usd"]:.4f}'
    formatted["Cache Hits"] = row["cache_hits"]
    formatted["Rate Limit Hits"] = row["rate_limit_hits"]
    formatted["License"] = ", ".join(row["license_types"])
    formatted["Status"] = ", ".join(row["statuses"])
    return formatted


def _format_total_row(
    report: UsageReport, *, show_mode: str, by_host: bool, color_output: bool
) -> dict[str, Any]:
    totals = {**report.totals, "period_start": "Total", "host": None}
    total = _format_report_row(totals, show_mode=show_mode, by_host=by_host)
    total["Period"] = _style("Total", "yellow", color_output)
    total["Host"] = ""
    total["Models"] = ""
    return total


def _report_window(days: int | None) -> str:
    if days is None:
        return "all collected history"
    return f"the last {days} days"


def _records_to_table(rows: list[dict[str, Any]], *, color_output: bool = False) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    widths = {
        header: max(len(header), *(len(str(row.get(header, ""))) for row in rows))
        for header in headers
    }
    lines = [
        "  ".join(_style(header, "cyan", color_output).ljust(widths[header]) for header in headers),
        "  ".join("-" * widths[header] for header in headers),
    ]
    for row in rows:
        lines.append("  ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers))
    return "\n".join(lines)


def _row_credit_remaining(row: dict[str, Any]) -> str:
    if "credit_remaining_percent" not in row:
        return ""
    return f'{float(row.get("credit_remaining_percent", 0)):.1f}%'


def _format_int(value: Any) -> str:
    return f"{int(value):,}"


def _style(value: str, color: str, enabled: bool) -> str:
    if not enabled:
        return value
    return click.style(value, fg=color)


if __name__ == "__main__":
    cli()
