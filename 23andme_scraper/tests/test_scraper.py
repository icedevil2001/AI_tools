from twentythreeandme_scraper.scraper import BODY_ROW_SELECTOR, build_data_url, dedupe_rows, should_stop_scraping
from twentythreeandme_scraper.parser import normalize_row


def test_dedupe_rows_keeps_unique_marker_assembly_position():
    row = normalize_row(
        {
            "Genes": "MT-ND1",
            "Marker": "rs123",
            "Assembly": "GRCh37",
            "Position": "3308",
            "Variants": "A or G",
            "Genotype": "AG",
        }
    )

    result = dedupe_rows([row, row])

    assert len(result) == 1


def test_should_stop_scraping_after_two_empty_iterations():
    assert should_stop_scraping(new_rows_count=0, consecutive_empty_pages=2, max_empty_pages=2) is True
    assert should_stop_scraping(new_rows_count=1, consecutive_empty_pages=2, max_empty_pages=2) is False


def test_build_data_url_uses_canonical_tools_data_route():
    login_url = "https://you.23andme.com/p/085d7e61a61b313d/tools/data/?chromosome=MT&offset=400"

    result = build_data_url(start_url=login_url, chromosome="1", offset=0)

    assert result == "https://you.23andme.com/tools/data/?chromosome=1&offset=0"


def test_build_data_url_ignores_auth_subdomain_from_login_flow():
    login_url = "https://auth.23andme.com/tools/data/?next=https%3A%2F%2Fauth.23andme.com%2Fauthorize%2F"

    result = build_data_url(start_url=login_url, chromosome="MT", offset=400)

    assert result == "https://you.23andme.com/tools/data/?chromosome=MT&offset=400"


def test_body_row_selector_skips_visual_header_row():
    assert BODY_ROW_SELECTOR == "#marker-table tbody tr:not(.js-visual-header)"
