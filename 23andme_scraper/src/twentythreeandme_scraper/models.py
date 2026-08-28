from __future__ import annotations

from dataclasses import dataclass


CSV_COLUMNS = ["Genes", "Marker", "Assembly", "Position", "Variants", "Genotype"]


@dataclass(frozen=True)
class RawDataRow:
    genes: str
    marker: str
    assembly: str
    position: str
    variants: str
    genotype: str

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.marker, self.assembly, self.position)

    def to_dict(self) -> dict[str, str]:
        return {
            "Genes": self.genes,
            "Marker": self.marker,
            "Assembly": self.assembly,
            "Position": self.position,
            "Variants": self.variants,
            "Genotype": self.genotype,
        }
