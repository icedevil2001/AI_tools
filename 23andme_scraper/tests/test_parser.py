from twentythreeandme_scraper.parser import normalize_assembly, normalize_row, split_rows_by_build


def test_normalize_row_keeps_requested_columns_in_shape():
    raw_row = {
        "Genes": "MT-ND1",
        "Marker": "rs123",
        "Assembly": "GRCh37",
        "Position": "3308",
        "Variants": "A or G",
        "Genotype": "AG",
    }

    result = normalize_row(raw_row)

    assert result.genes == "MT-ND1"
    assert result.marker == "rs123"
    assert result.assembly == "GRCh37"
    assert result.position == "3308"
    assert result.variants == "A or G"
    assert result.genotype == "AG"


def test_normalize_assembly_maps_common_build_labels():
    assert normalize_assembly("GRCh37") == "build37"
    assert normalize_assembly("Build 38") == "build38"
    assert normalize_assembly("unknown") is None


def test_split_rows_by_build_routes_mixed_rows():
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
                "Assembly": "Build 38",
                "Position": "4470",
                "Variants": "C or T",
                "Genotype": "CT",
            }
        ),
    ]

    build37, build38 = split_rows_by_build(rows)

    assert [row.marker for row in build37] == ["rs123"]
    assert [row.marker for row in build38] == ["rs456"]
