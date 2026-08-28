import csv

from twentythreeandme_scraper.output import write_split_csvs
from twentythreeandme_scraper.parser import normalize_row


def test_write_split_csvs_writes_requested_headers_and_rows(tmp_path):
    rows = [
        normalize_row(
            {
                "Genes": "MT-ND1",
                "Marker": "rs123",
                "Assembly": "GRCh37",
                "Position": "3308",
                "Variants": "A or G",
                "Genotype": "AG",
            }
        ),
        normalize_row(
            {
                "Genes": "MT-ND2",
                "Marker": "rs456",
                "Assembly": "GRCh38",
                "Position": "4470",
                "Variants": "C or T",
                "Genotype": "CT",
            }
        ),
    ]

    build37_path, build38_path = write_split_csvs(rows, tmp_path)

    with build37_path.open(newline="") as handle:
        build37_rows = list(csv.DictReader(handle))
    with build38_path.open(newline="") as handle:
        build38_rows = list(csv.DictReader(handle))

    assert build37_rows == [
        {
            "Genes": "MT-ND1",
            "Marker": "rs123",
            "Assembly": "GRCh37",
            "Position": "3308",
            "Variants": "A or G",
            "Genotype": "AG",
        }
    ]
    assert build38_rows == [
        {
            "Genes": "MT-ND2",
            "Marker": "rs456",
            "Assembly": "GRCh38",
            "Position": "4470",
            "Variants": "C or T",
            "Genotype": "CT",
        }
    ]
