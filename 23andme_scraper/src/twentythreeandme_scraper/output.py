from __future__ import annotations

import csv
from pathlib import Path

from twentythreeandme_scraper.models import CSV_COLUMNS, RawDataRow
from twentythreeandme_scraper.parser import split_rows_by_build


def write_split_csvs(rows: list[RawDataRow], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    build37_rows, build38_rows = split_rows_by_build(rows)
    build37_path = output_dir / "build37.csv"
    build38_path = output_dir / "build38.csv"
    _write_csv(build37_path, build37_rows)
    _write_csv(build38_path, build38_rows)
    return build37_path, build38_path


def _write_csv(path: Path, rows: list[RawDataRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(row.to_dict() for row in rows)
