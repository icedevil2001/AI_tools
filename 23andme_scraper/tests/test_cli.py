from click.testing import CliRunner

from twentythreeandme_scraper.main import cli


def test_scrape_command_uses_defaults_and_invokes_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run_scrape(**kwargs):
        captured.update(kwargs)
        return tmp_path / "build37.csv", tmp_path / "build38.csv"

    monkeypatch.setattr("twentythreeandme_scraper.main.run_scrape", fake_run_scrape)

    runner = CliRunner()
    result = runner.invoke(cli, ["scrape", "--start-url", "https://example.com/data"])

    assert result.exit_code == 0
    assert captured["start_url"] == "https://example.com/data"
    assert captured["headed"] is True
    assert captured["output_dir"].name == "23andme"
    assert captured["state_file"].name == "23andme_auth.json"


def test_scrape_command_accepts_custom_state_file(monkeypatch, tmp_path):
    captured = {}

    def fake_run_scrape(**kwargs):
        captured.update(kwargs)
        return tmp_path / "build37.csv", tmp_path / "build38.csv"

    monkeypatch.setattr("twentythreeandme_scraper.main.run_scrape", fake_run_scrape)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "scrape",
            "--start-url",
            "https://example.com/data",
            "--state-file",
            str(tmp_path / "saved_state.json"),
        ],
    )

    assert result.exit_code == 0
    assert captured["state_file"].name == "saved_state.json"


def test_help_renders():
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "scrape" in result.output
