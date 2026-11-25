import os
import stat
import sys
from unittest.mock import patch

import pytest


def test_resolve_config_from_param():
    from somark._config import resolve_config
    cfg = resolve_config(api_key="sk-test", base_url="https://custom.api", timeout=30.0, max_retries=1)
    assert cfg["api_key"] == "sk-test"
    assert cfg["base_url"] == "https://custom.api"
    assert cfg["timeout"] == 30.0
    assert cfg["max_retries"] == 1


def test_resolve_config_from_env():
    from somark._config import resolve_config
    with patch.dict(os.environ, {"SOMARK_API_KEY": "sk-env-key", "SOMARK_BASE_URL": "https://env.api"}, clear=True):
        with patch("somark._config._load_toml_config", return_value={}):
            cfg = resolve_config()
    assert cfg["api_key"] == "sk-env-key"
    assert cfg["base_url"] == "https://env.api"


def test_resolve_config_defaults():
    from somark._config import resolve_config, DEFAULT_BASE_URL, DEFAULT_TIMEOUT, DEFAULT_MAX_RETRIES
    with patch.dict(os.environ, {}, clear=True):
        with patch("somark._config._load_toml_config", return_value={}):
            cfg = resolve_config()
    assert cfg["api_key"] is None
    assert cfg["active_mode"] == "auto"
    assert cfg["request_blocked"]
    assert cfg["base_url"] in ("", None)
    assert cfg["base_url"] != DEFAULT_BASE_URL
    assert cfg["timeout"] == DEFAULT_TIMEOUT
    assert cfg["max_retries"] == DEFAULT_MAX_RETRIES


def test_resolve_config_priority():
    from somark._config import resolve_config
    file_cfg = {
        "active_mode": "auto",
        "api_key": "sk-file",
        "base_url": "https://somark.cn/api/v1",
    }
    with patch.dict(os.environ, {"SOMARK_API_KEY": "sk-env"}, clear=True):
        with patch("somark._config._load_toml_config", return_value=file_cfg):
            cfg = resolve_config(api_key="sk-param")
    assert cfg["api_key"] == "sk-param"  # param wins
    assert cfg["base_url"] == "https://somark.cn/api/v1"


def test_list_resolved_config_uses_schema_sources():
    from somark._config import list_resolved_config, DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES

    with patch.dict(os.environ, {"SOMARK_TIMEOUT": "45"}, clear=True):
        with patch("somark._config._load_toml_config", return_value={"api_key": "sk-file"}):
            entries = list_resolved_config()

    assert entries == [
        {"key": "api_key", "value": "sk-file", "source": "file"},
        {"key": "base_url", "value": DEFAULT_BASE_URL, "source": "default"},
        {"key": "timeout", "value": "45", "source": "env"},
        {"key": "max_retries", "value": str(DEFAULT_MAX_RETRIES), "source": "default"},
    ]


def test_resolve_config_validates_base_url_from_env():
    from somark._config import resolve_config

    with patch.dict(os.environ, {"SOMARK_BASE_URL": "not-a-url"}, clear=True):
        with patch("somark._config._load_toml_config", return_value={}):
            try:
                resolve_config()
            except ValueError as exc:
                assert 'Invalid base_url "not-a-url"' in str(exc)
            else:
                raise AssertionError("resolve_config should reject invalid base_url")


def test_save_config_sets_private_permissions(tmp_path):
    from somark._config import save_config

    config_file = tmp_path / "config.toml"
    with patch("somark._config.CONFIG_FILE", config_file):
        save_config(api_key="sk-private-key")

    if sys.platform == "win32":
        pytest.skip("Windows does not store POSIX 0600 permission bits")
    mode = stat.S_IMODE(config_file.stat().st_mode)
    assert mode == 0o600


def test_mask_config_value_hides_api_key():
    from somark._config import mask_config_value

    assert mask_config_value("api_key", "sk-1234567890") == "sk-1...7890"
    assert mask_config_value("api_key", "sk-test") == "***"
    assert mask_config_value("base_url", "https://somark.tech") == "https://somark.tech"
