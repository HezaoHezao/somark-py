"""Suggested-review leftovers: OXR page count, auth JSON, profile names."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from somark._config import OXR_DEFAULT_BASE_URL, config_file_for_profile, enforce_oxr_input_limits
from somark._exceptions import FileTooLargeError
from somark.resources.parser import DocumentParser

runner = CliRunner()


def _app():
    from somark.cli.main import app

    return app


def test_oxr_refuses_pdf_when_page_count_cannot_be_read(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.0")
    with patch("somark._config._pdf_page_count", return_value=None):
        with pytest.raises(FileTooLargeError, match="could not confirm the PDF page count"):
            enforce_oxr_input_limits([str(pdf)])


def test_oxr_refuses_pdf_over_20_pages(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.0")
    with patch("somark._config._pdf_page_count", return_value=21):
        with pytest.raises(FileTooLargeError, match="21 pages"):
            enforce_oxr_input_limits([str(pdf)])


def test_sdk_parse_enforces_oxr_limits_only_for_oxr_host(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.0")
    oxr = MagicMock()
    oxr.api_key = None
    oxr.base_url = OXR_DEFAULT_BASE_URL
    oxr.request_blocked = None
    with patch("somark._config._pdf_page_count", return_value=None):
        with pytest.raises(FileTooLargeError, match="could not confirm"):
            DocumentParser(oxr).parse(file=str(pdf))
    oxr.post.assert_not_called()

    official = MagicMock()
    official.api_key = "sk-official"
    official.base_url = "https://somark.cn/api/v1"
    official.request_blocked = None
    official.post.return_value = {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": "abc123",
            "error": None,
            "metadata": {"page_num": 1, "file_type": ".pdf"},
            "result": {"file_name": "a.pdf", "imgs": [], "outputs": {"markdown": "ok", "json": {}, "zip": None}},
        },
    }
    with patch("somark._config._pdf_page_count", return_value=None):
        DocumentParser(official).parse(file=str(pdf))
    official.post.assert_called_once()


def test_auth_status_json_is_one_line(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    monkeypatch.setattr("somark._config.CONFIG_FILE", config)
    long_url = "https://private.example/" + ("x" * 180)
    config.write_text(
        f'active_mode = "private"\nprivate_base_url = "{long_url}"\nprivate_api_key = ""\n',
        encoding="utf-8",
    )
    result = runner.invoke(_app(), ["auth", "status", "--output", "json"])
    assert result.exit_code == 0
    body = result.stdout.strip()
    assert "\n" not in body
    payload = json.loads(body)
    assert payload["base_url"] == long_url
    assert payload["method"] == "private"


def test_auth_status_rejects_unknown_output():
    result = runner.invoke(_app(), ["auth", "status", "--output", "yaml"])
    assert result.exit_code != 0
    assert "text or json" in result.output


def test_global_output_flag_is_removed():
    result = runner.invoke(_app(), ["--help"])
    assert result.exit_code == 0
    assert "Global machine output" not in result.output
    bad = runner.invoke(_app(), ["--output", "json", "auth", "status"])
    assert bad.exit_code != 0


def test_profile_name_must_stay_inside_config_dir():
    with pytest.raises(ValueError, match="Invalid profile"):
        config_file_for_profile("../../evil")
    with pytest.raises(ValueError, match="Invalid profile"):
        config_file_for_profile("work/buddy")
    path = config_file_for_profile("workbuddy")
    assert path.name == "workbuddy.toml"
    assert path.parent.name == "profiles"


def test_cli_rejects_traversal_profile():
    result = runner.invoke(_app(), ["--profile", "../../evil", "auth", "status"])
    assert result.exit_code != 0
    assert "Invalid profile" in result.output
