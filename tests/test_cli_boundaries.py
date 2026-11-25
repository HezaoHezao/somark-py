"""Happy path and boundary checks for the oxr / auto / private CLI.

No network. Config is redirected into tmp_path. HTTP is either blocked before
the client is used, or replaced with a mock transport.
"""

import json
import os
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from somark._config import (
    OXR_DEFAULT_BASE_URL,
    OXR_MAX_FILE_BYTES,
    OXR_MAX_PAGES,
    classify_destination,
    config_file_for_profile,
    enforce_oxr_input_limits,
    resolve_config,
)
from somark._exceptions import AuthenticationError, FileTooLargeError, UnsupportedFileError
from somark._probe import probe_official_base_url

runner = CliRunner()
ENV_KEYS = (
    "SOMARK_API_KEY",
    "SOMARK_BASE_URL",
    "SOMARK_API_BASE_URL",
    "SOMARK_PRIVATE_BASE_URL",
    "SOMARK_PRIVATE_API_KEY",
)


def _app():
    from somark.cli.main import app

    return app


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    home = tmp_path / "somark-home"
    home.mkdir()
    monkeypatch.setattr("somark._config.CONFIG_DIR", home)
    monkeypatch.setattr("somark._config.CONFIG_FILE", home / "config.toml")
    monkeypatch.setattr("somark._config._ACTIVE_PROFILE", None)
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("somark._config._pdf_page_count", lambda _path: 1)
    return home


def _write_config(home, text: str) -> None:
    (home / "config.toml").write_text(text, encoding="utf-8")


def _read_config(home) -> str:
    path = home / "config.toml"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _pdf(tmp_path, name="a.pdf", payload=b"%PDF-1.4\n"):
    path = tmp_path / name
    path.write_bytes(payload)
    return path


# --- destination classification -------------------------------------------------


def test_classify_destination_official_oxr_and_private():
    assert classify_destination("https://somark.cn/api/v1") == "official"
    assert classify_destination("https://somark.tech/api/v1/") == "official"
    assert classify_destination(OXR_DEFAULT_BASE_URL) == "oxr"
    assert classify_destination("https://private.example/api/v1") == "private"


@pytest.mark.parametrize("url", ["", "ftp://somark.cn/api", "not-a-url", "   "])
def test_classify_destination_rejects_non_http(url):
    with pytest.raises(ValueError, match="Invalid base url"):
        classify_destination(url)


def test_free_oxr_substring_is_not_the_free_endpoint():
    assert classify_destination("https://evil.example/free-oxr/api") == "private"


def test_probe_ignores_non_sk_key_without_calling_network():
    calls = []

    def _request(base, key, timeout=0):
        calls.append(base)
        return True

    assert probe_official_base_url("local-key", request_usage=_request) is None
    assert calls == []


def test_probe_uses_cn_before_ai_and_skips_a_failing_site():
    seen = []

    def _cn_ok(base, key, timeout=0):
        seen.append(base)
        return "somark.cn" in base

    assert probe_official_base_url("sk-test", request_usage=_cn_ok) == "https://somark.cn/api/v1"
    assert seen == ["https://somark.cn/api/v1"]

    def _only_ai(base, key, timeout=0):
        if "somark.cn" in base:
            raise RuntimeError("cn down")
        return "somark.ai" in base

    assert probe_official_base_url("sk-test", request_usage=_only_ai) == "https://somark.ai/api/v1"


def test_probe_returns_none_when_both_sites_reject():
    assert probe_official_base_url("sk-test", request_usage=lambda *args, **kwargs: False) is None


# --- happy path -----------------------------------------------------------------


def test_fresh_parse_is_blocked_before_http(isolated, tmp_path):
    pdf = _pdf(tmp_path)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"code": 0, "data": {}})

    from somark import SoMark

    client = SoMark(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(AuthenticationError, match="somark login"):
        client.parser.parse(str(pdf))
    client.close()
    assert seen == {}
    cfg = resolve_config()
    assert cfg["active_mode"] == "auto"
    assert cfg["base_url"] == ""
    assert cfg["api_key"] is None


def test_login_no_open_probes_and_saves_official_mode(isolated):
    with patch("somark.cli.cmd_login.probe_official_base_url", return_value="https://somark.ai/api/v1"):
        result = runner.invoke(_app(), ["login", "--no-open", "--api-key", "  sk-piped  "])
    assert result.exit_code == 0, result.output
    assert "active_mode=auto" in result.output
    text = _read_config(isolated)
    assert 'api_key = "sk-piped"' in text
    assert "https://somark.ai/api/v1" in text
    cfg = resolve_config()
    assert cfg["active_mode"] == "auto"
    assert cfg["base_url"] == "https://somark.ai/api/v1"
    assert cfg["api_key"] == "sk-piped"


def test_login_stdin_key_is_not_treated_as_a_region(isolated):
    with patch("somark.cli.cmd_login.probe_official_base_url", return_value="https://somark.cn/api/v1"):
        result = runner.invoke(_app(), ["login", "--no-open"], input="sk-from-stdin\n")
    assert result.exit_code == 0, result.output
    assert resolve_config()["api_key"] == "sk-from-stdin"


def test_private_login_activates_private_and_parse_stays_there(isolated, tmp_path):
    result = runner.invoke(
        _app(),
        ["login", "--url", "https://private.example/api/v1/", "--api-key", "local-key"],
    )
    assert result.exit_code == 0, result.output
    assert "active_mode=private" in result.output
    cfg = resolve_config()
    assert cfg["base_url"] == "https://private.example/api/v1"
    assert cfg["api_key"] == "local-key"

    pdf = _pdf(tmp_path)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "task_id": "t1",
                    "metadata": {"page_num": 1},
                    "result": {"outputs": {"markdown": "ok"}},
                },
            },
        )

    from somark import SoMark

    client = SoMark(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        client.parser.parse(str(pdf))
    finally:
        client.close()
    assert seen["url"] == "https://private.example/api/v1/parse/sync"
    assert b"local-key" in seen["body"]


def test_use_oxr_then_parse_small_pdf(isolated, tmp_path):
    _write_config(isolated, 'active_mode = "oxr"\n')
    pdf = _pdf(tmp_path)
    mock_client = MagicMock()
    mock_client.parser.parse.return_value._content_for_format.return_value = "# ok\n"
    with patch("somark.cli._runtime.make_client", return_value=mock_client):
        result = runner.invoke(_app(), ["parse", str(pdf)])
    assert result.exit_code == 0, result.output
    assert "# ok" in result.output
    mock_client.parser.parse.assert_called_once()


def test_auth_status_json_and_logout(isolated):
    _write_config(
        isolated,
        'active_mode = "auto"\napi_key = "sk-official"\nbase_url = "https://somark.cn/api/v1"\n',
    )
    status = runner.invoke(_app(), ["auth", "status", "--output", "json"])
    assert status.exit_code == 0, status.output
    payload = json.loads(status.stdout.strip())
    assert payload["logged_in"] is True
    assert payload["active_mode"] == "auto"
    assert payload["base_url"] == "https://somark.cn/api/v1"
    assert "\n" not in status.stdout.strip()

    logged_out = runner.invoke(_app(), ["logout"])
    assert logged_out.exit_code == 0, logged_out.output
    again = runner.invoke(_app(), ["auth", "status", "--output", "json"])
    body = json.loads(again.stdout.strip())
    assert again.exit_code == 1
    assert body["logged_in"] is False
    assert body["active_mode"] == "auto"
    assert "sk-official" not in _read_config(isolated)


def test_use_lists_modes_and_api_alias_means_auto(isolated):
    _write_config(
        isolated,
        'active_mode = "auto"\napi_key = "sk-official"\nbase_url = "https://somark.cn/api/v1"\n',
    )
    shown = runner.invoke(_app(), ["use"])
    assert shown.exit_code == 0, shown.output
    assert "active_mode = auto" in shown.output
    assert "oxr" in shown.output and "private" in shown.output

    switched = runner.invoke(_app(), ["use", "api"])
    assert switched.exit_code == 0, switched.output
    assert 'active_mode = "auto"' in _read_config(isolated)


# --- credential boundaries ------------------------------------------------------


def test_official_login_rejects_bad_keys_and_writes_nothing(isolated):
    for args in (
        ["login", "--no-open", "--api-key", ""],
        ["login", "--no-open", "--api-key", "not-sk"],
        ["login", "--no-open", "--api-key", "   "],
    ):
        result = runner.invoke(_app(), args)
        assert result.exit_code == 1, result.output
        assert "sk-" in result.output
    assert not (isolated / "config.toml").exists()


def test_probe_failure_does_not_save(isolated):
    with patch("somark.cli.cmd_login.probe_official_base_url", return_value=None):
        result = runner.invoke(_app(), ["login", "--no-open", "--api-key", "sk-dead"])
    assert result.exit_code == 1, result.output
    assert "Nothing was saved" in result.output
    assert not (isolated / "config.toml").exists()


def test_invalid_login_url_is_rejected(isolated):
    result = runner.invoke(_app(), ["login", "--url", "ftp://example.test/api"])
    assert result.exit_code == 1, result.output
    assert "http://" in result.output
    assert not (isolated / "config.toml").exists()


def test_login_url_oxr_switches_without_a_key(isolated):
    result = runner.invoke(_app(), ["login", "--url", OXR_DEFAULT_BASE_URL])
    assert result.exit_code == 0, result.output
    cfg = resolve_config()
    assert cfg["active_mode"] == "oxr"
    assert cfg["base_url"] == OXR_DEFAULT_BASE_URL
    assert cfg["api_key"] is None


def test_replacing_private_url_with_blank_key_drops_the_old_key(isolated, monkeypatch):
    _write_config(
        isolated,
        "\n".join(
            [
                'active_mode = "private"',
                'private_base_url = "https://old.example/api/v1"',
                'private_api_key = "sk-old"',
            ]
        )
        + "\n",
    )
    result = runner.invoke(
        _app(),
        ["login", "--url", "https://new-host.example/api/v1", "--api-key", ""],
    )
    assert result.exit_code == 0, result.output
    monkeypatch.setenv("SOMARK_PRIVATE_API_KEY", "sk-old")
    monkeypatch.setenv("SOMARK_API_KEY", "sk-official")
    cfg = resolve_config()
    assert cfg["active_mode"] == "private"
    assert cfg["base_url"] == "https://new-host.example/api/v1"
    assert cfg["api_key"] is None


def test_private_mode_ignores_official_env_key(isolated, monkeypatch):
    _write_config(
        isolated,
        "\n".join(
            [
                'active_mode = "private"',
                'private_base_url = "https://private.example/api/v1"',
                'private_api_key = "local-key"',
            ]
        )
        + "\n",
    )
    monkeypatch.setenv("SOMARK_API_KEY", "sk-official")
    monkeypatch.setenv("SOMARK_BASE_URL", "https://somark.cn/api/v1")
    cfg = resolve_config()
    assert cfg["base_url"] == "https://private.example/api/v1"
    assert cfg["api_key"] == "local-key"


def test_env_base_url_without_key_does_not_upload_to_oxr(isolated):
    with patch.dict(os.environ, {"SOMARK_BASE_URL": "https://secret.internal/api/v1"}, clear=True):
        cfg = resolve_config()
    assert cfg["request_blocked"]
    assert cfg["base_url"] == ""
    assert OXR_DEFAULT_BASE_URL not in (cfg["base_url"] or "")


def test_private_without_url_blocks_before_request(isolated, tmp_path):
    _write_config(isolated, 'active_mode = "private"\nprivate_api_key = "local-key"\n')
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"code": 0})

    from somark import SoMark

    client = SoMark(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(AuthenticationError, match="private_base_url"):
        client.parser.parse(str(_pdf(tmp_path)))
    client.close()
    assert seen == {}
    assert resolve_config()["api_key"] is None


def test_use_rejects_unknown_and_unready_modes(isolated):
    unknown = runner.invoke(_app(), ["use", "prod"])
    assert unknown.exit_code == 1
    assert "auto | oxr | private" in unknown.output

    not_ready = runner.invoke(_app(), ["use", "auto"])
    assert not_ready.exit_code == 1
    assert "somark login" in not_ready.output

    no_private = runner.invoke(_app(), ["use", "private"])
    assert no_private.exit_code == 1
    assert "login --url" in no_private.output


def test_keyless_private_is_ready_and_sends_no_key(isolated, tmp_path):
    result = runner.invoke(_app(), ["login", "--url", "https://private.example/api/v1", "--api-key", ""])
    assert result.exit_code == 0, result.output
    status = runner.invoke(_app(), ["auth", "status", "--output", "json"])
    payload = json.loads(status.stdout.strip())
    assert status.exit_code == 0
    assert payload["logged_in"] is True
    assert payload["method"] == "private"

    seen = {}

    def handler(request):
        seen["body"] = request.content
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"code": 0, "data": {"task_id": "t", "metadata": {"page_num": 1}, "result": {"outputs": {"markdown": "x"}}}},
        )

    from somark import SoMark

    client = SoMark(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        client.parser.parse(str(_pdf(tmp_path)))
    finally:
        client.close()
    assert seen["url"].startswith("https://private.example/api/v1/")
    assert b"api_key" not in seen["body"]


# --- parse limits and bad input -------------------------------------------------


def test_missing_file_is_reported_and_client_is_not_called(isolated, tmp_path):
    _write_config(isolated, 'active_mode = "oxr"\n')
    mock_client = MagicMock()
    missing = tmp_path / "nope.pdf"
    with patch("somark.cli._runtime.make_client", return_value=mock_client):
        result = runner.invoke(_app(), ["parse", str(missing)])
    assert result.exit_code == 1
    assert "File not found" in result.output
    assert "Errno" not in result.output
    mock_client.parser.parse.assert_not_called()


def test_oxr_rejects_format_size_and_page_boundaries(isolated, tmp_path, monkeypatch):
    _write_config(isolated, 'active_mode = "oxr"\n')
    assert OXR_MAX_FILE_BYTES == 10 * 1024 * 1024
    assert OXR_MAX_PAGES == 20

    no_suffix = tmp_path / "nosuffix"
    no_suffix.write_bytes(b"hello")
    docx = tmp_path / "a.docx"
    docx.write_bytes(b"PK")
    mock_client = MagicMock()
    with patch("somark.cli._runtime.make_client", return_value=mock_client):
        bare = runner.invoke(_app(), ["parse", str(no_suffix)])
        office = runner.invoke(_app(), ["parse", str(docx)])
    assert bare.exit_code == 1 and "(no suffix)" in bare.output
    assert office.exit_code == 1 and ".docx" in office.output
    mock_client.parser.parse.assert_not_called()

    monkeypatch.setattr("somark._config.OXR_MAX_FILE_BYTES", 4)
    small = tmp_path / "small.pdf"
    exact = tmp_path / "exact.pdf"
    over = tmp_path / "over.pdf"
    small.write_bytes(b"123")
    exact.write_bytes(b"1234")
    over.write_bytes(b"12345")
    enforce_oxr_input_limits([str(small), str(exact)])
    with pytest.raises(FileTooLargeError, match="Refuse to parse"):
        enforce_oxr_input_limits([str(over)])
    monkeypatch.setattr("somark._config.OXR_MAX_FILE_BYTES", 10 * 1024 * 1024)

    pdf = _pdf(tmp_path, "pages.pdf")
    monkeypatch.setattr("somark._config._pdf_page_count", lambda _path: 20)
    enforce_oxr_input_limits([str(pdf)])
    monkeypatch.setattr("somark._config._pdf_page_count", lambda _path: 21)
    with pytest.raises(FileTooLargeError, match="21 pages"):
        enforce_oxr_input_limits([str(pdf)])
    monkeypatch.setattr("somark._config._pdf_page_count", lambda _path: None)
    with pytest.raises(FileTooLargeError, match="could not confirm"):
        enforce_oxr_input_limits([str(pdf)])


def test_explicit_private_base_url_skips_oxr_format_ban(isolated, tmp_path):
    _write_config(isolated, 'active_mode = "oxr"\n')
    docx = tmp_path / "a.docx"
    docx.write_bytes(b"PK")
    mock_client = MagicMock()
    mock_client.parser.parse.return_value._content_for_format.return_value = "ok"
    with patch("somark.cli._runtime.make_client", return_value=mock_client):
        result = runner.invoke(
            _app(),
            ["--base-url", "https://private.example/api/v1", "parse", str(docx)],
        )
    assert result.exit_code == 0, result.output
    mock_client.parser.parse.assert_called_once()


def test_sdk_oxr_limit_runs_before_post(isolated, tmp_path):
    pdf = _pdf(tmp_path)
    http = MagicMock()
    http.api_key = None
    http.base_url = OXR_DEFAULT_BASE_URL
    http.request_blocked = None
    http.private_base_url = None
    with patch("somark._config._pdf_page_count", return_value=None):
        from somark.resources.parser import DocumentParser

        with pytest.raises(FileTooLargeError):
            DocumentParser(http).parse(file=str(pdf))
    http.post.assert_not_called()


def test_batch_stops_when_one_file_is_missing(isolated, tmp_path):
    _write_config(isolated, 'active_mode = "oxr"\n')
    present = _pdf(tmp_path, "a.pdf")
    missing = tmp_path / "missing.pdf"
    out = tmp_path / "out"
    out.mkdir()
    mock_client = MagicMock()
    with patch("somark.cli._runtime.make_client", return_value=mock_client):
        result = runner.invoke(_app(), ["parse", str(present), str(missing), "--out", str(out)])
    assert result.exit_code == 1
    assert "File not found" in result.output
    assert "Summary:" not in result.output
    mock_client.parser.parse.assert_not_called()


# --- output and profile ---------------------------------------------------------


@pytest.mark.parametrize("flag", ["yaml", ""])
def test_auth_output_rejects_values_other_than_text_or_json(isolated, flag):
    result = runner.invoke(_app(), ["auth", "status", "--output", flag])
    assert result.exit_code == 2
    assert "text or json" in result.output


def test_auth_output_json_is_case_insensitive(isolated):
    result = runner.invoke(_app(), ["auth", "status", "--output", "JSON"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout.strip())
    assert payload["logged_in"] is False


def test_long_url_json_stays_one_machine_readable_line(isolated):
    long_url = "https://private.example/" + ("segment-" * 30) + "api/v1"
    _write_config(
        isolated,
        f'active_mode = "private"\nprivate_base_url = "{long_url}"\nprivate_api_key = ""\n',
    )
    result = runner.invoke(_app(), ["auth", "status", "--output", "json"])
    assert result.exit_code == 0, result.output
    assert "\n" not in result.stdout.strip()
    assert json.loads(result.stdout)["base_url"] == long_url


def test_profile_names_cannot_escape_the_config_dir(isolated):
    with pytest.raises(ValueError, match="Invalid profile"):
        config_file_for_profile("../../evil")
    with pytest.raises(ValueError, match="Invalid profile"):
        config_file_for_profile("C:/outside/evil")
    path = config_file_for_profile("workbuddy")
    assert path.parent == (isolated / "profiles").resolve()

    result = runner.invoke(_app(), ["--profile", "../evil", "auth", "status"])
    assert result.exit_code == 1
    assert "Invalid profile" in result.output
    assert not (isolated / "evil.toml").exists()


def test_supported_image_suffix_is_allowed_on_oxr(tmp_path, monkeypatch):
    monkeypatch.setattr("somark._config._pdf_page_count", lambda _path: 1)
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG")
    enforce_oxr_input_limits([str(image)])


def test_oxr_still_rejects_uppercase_office_suffix(tmp_path):
    office = tmp_path / "A.DOCX"
    office.write_bytes(b"PK")
    with pytest.raises(UnsupportedFileError, match=".docx"):
        enforce_oxr_input_limits([str(office)])
