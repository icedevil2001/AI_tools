from __future__ import annotations

from twentythreeandme_scraper.models import RawDataRow


def normalize_assembly(value: str) -> str | None:
    cleaned = (value or "").strip().lower()
    if cleaned in {"grch37", "build 37", "build37", "37"}:
        return "build37"
    if cleaned in {"grch38", "build 38", "build38", "38"}:
        return "build38"
    return None


def normalize_row(raw_row: dict[str, str]) -> RawDataRow:
    return RawDataRow(
        genes=(raw_row.get("Genes") or "").strip(),
        marker=(raw_row.get("Marker") or "").strip(),
        assembly=(raw_row.get("Assembly") or "").strip(),
        position=(raw_row.get("Position") or "").strip(),
        variants=(raw_row.get("Variants") or "").strip(),
        genotype=(raw_row.get("Genotype") or "").strip(),
    )


def split_rows_by_build(rows: list[RawDataRow]) -> tuple[list[RawDataRow], list[RawDataRow]]:
    build37: list[RawDataRow] = []
    build38: list[RawDataRow] = []

    for row in rows:
        bucket = normalize_assembly(row.assembly)
        if bucket == "build37":
            build37.append(row)
        elif bucket == "build38":
            build38.append(row)

    return build37, build38
